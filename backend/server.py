"""FastAPI server exposing the scrap pipeline as a simple web API.

uv run python server.py

Endpoints:
- POST /api/search  {"query": str, "count": 1-250}  -> starts a job, returns {"id"}
- GET  /api/jobs/{id}  -> live status, phase, log tail and results
- GET  /api/jobs       -> summary of all jobs
- GET  /api/results    -> results from the current output.json
"""

import json
import os
import subprocess
import sys
import threading
import uuid

import uvicorn
from dotenv import load_dotenv
from fastapi import Body, FastAPI

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "output.json")
PAGE_SIZE = 25
MAX_DOCS = 250
LOG_TAIL = 300

app = FastAPI(title="scrap-ieee API", version="0.1.0")

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def log(job: dict, message: str) -> None:
    """Append a message to the job's log."""
    with JOBS_LOCK:
        job["log"].append(message)


def run_script(job: dict, cmd: list[str], phase: str) -> bool:
    """Run a subprocess command, logging its output and updating the job phase."""
    with JOBS_LOCK:
        job["phase"] = phase
    log(job, f"=== {phase} ===")
    proc = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log(job, line.rstrip())
    proc.wait()
    log(job, f"=== {phase} finished (exit {proc.returncode}) ===")
    return proc.returncode == 0


def pdf_link(entry: dict) -> tuple[str | None, str]:
    """Return (pdf_url, source) for a paper."""
    doi = entry.get("doi", "")
    if entry.get("sci_net"):
        return f"https://sci-net.xyz/{doi}", "sci-net"
    sci_hub = entry.get("sci_hub", "")
    if sci_hub:
        if sci_hub.startswith("//"):
            sci_hub = "https:" + sci_hub
        return sci_hub, "sci-hub"
    status = entry.get("status", "")
    if status == "not-found":
        return None, "not-found"
    if status == "not-checked":
        return None, "not-checked"
    return None, "pending"


def load_results() -> list[dict]:
    """Load and enrich output.json with the user-facing pdf url and source."""
    if not os.path.exists(OUTPUT_FILE):
        return []
    try:
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    for entry in data:
        link, source = pdf_link(entry)
        entry["pdf_link"] = link
        entry["source"] = source
    return data


def run_pipeline(job: dict, query: str, count: int) -> None:
    """Run the full pipeline for a given query and count, updating the job dict."""
    pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
    scraper_cmd = [
        sys.executable,
        os.path.join(BASE_DIR, "scraper.py"),
        "--query", query,
        "--pages-from", "1",
        "--pages-to", str(pages),
    ]
    if not run_script(job, scraper_cmd, "searching IEEE Xplore"):
        with JOBS_LOCK:
            job["status"] = "failed"
        return

    cookie = os.environ.get("SCINET_COOKIE")
    if cookie:
        # Phase 4: check sci-net / sci-hub availability
        if not run_script(
            job,
            [sys.executable, os.path.join(BASE_DIR, "scinet.py"), "--cookie", cookie, "--only-query"],
            "checking sci-net / sci-hub",
        ):
            with JOBS_LOCK:
                job["status"] = "failed"
            return
    else:
        log(job, "SCINET_COOKIE not set - skipping the sci-net availability check.")
        data = load_results()
        for entry in data:
            entry["status"] = "not-checked"
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Phase 5: download PDFs not found anywhere.
    # Headed + auto-detect: if the saved IEEE session is stale, a browser opens
    # and waits for sign-in (up to LOGIN_WAIT seconds). No stdin needed.
    if not run_script(
        job,
        scraper_cmd + ["--download-missing", "--login-wait", os.environ.get("LOGIN_WAIT", "300")],
        "downloading missing PDFs",
    ):
        with JOBS_LOCK:
            job["status"] = "failed"
        return

    if cookie:
        # Phases 6-7: register upload tickets and upload PDFs
        if not run_script(
            job,
            [sys.executable, os.path.join(BASE_DIR, "scinet.py"), "--cookie", cookie, "--skip-query"],
            "registering and uploading PDFs",
        ):
            with JOBS_LOCK:
                job["status"] = "failed"
            return
    else:
        log(job, "SCINET_COOKIE not set - skipping upload.")

    with JOBS_LOCK:
        job["status"] = "completed"
        job["results"] = load_results()


@app.post("/api/search")
def start_search(
    payload: dict = Body(...),
) -> dict:
    """Start a new search job with the given query and count."""
    query = str(payload.get("query", "")).strip()
    count = int(payload.get("count", 25))
    if not query:
        return {"error": "query is required"}
    if count < 1 or count > MAX_DOCS:
        return {"error": f"count must be between 1 and {MAX_DOCS}"}

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "status": "running",
        "phase": "searching IEEE Xplore",
        "params": {"query": query, "count": count},
        "log": [],
        "results": None,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job

    threading.Thread(
        target=run_pipeline, args=(job, query, count), daemon=True
    ).start()
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    """Return the status, phase, log tail and results for a given job id."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return {"error": "Job not found", "id": job_id}
    with JOBS_LOCK:
        return {
            "id": job["id"],
            "status": job["status"],
            "phase": job["phase"],
            "params": job["params"],
            "log": job["log"][-LOG_TAIL:],
            "results": job["results"],
        }


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    """Return a summary of all jobs with their id, status, phase, and params."""
    with JOBS_LOCK:
        return [
            {
                "id": j["id"],
                "status": j["status"],
                "phase": j["phase"],
                "params": j["params"],
            }
            for j in JOBS.values()
        ]


@app.get("/api/results")
def results() -> list[dict]:
    """Return the current results from output.json, enriched with pdf_link and source."""
    return load_results()


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )
