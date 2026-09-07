"""Query sci-net.xyz to check which DOIs have been uploaded."""

# uv run python scinet.py --cookie 'connect.sid=...'
# --cookie (optional): The connect.sid cookie for sci-net.xyz (or set SCINET_COOKIE in .env).
# --only-query (optional): Run Phase 4 only (query sci-net/sci-hub), then exit.
# --skip-query (optional): Skip Phase 4, run Phases 6-7 (register + upload) only.

import argparse
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


SCINET_URL = "https://sci-net.xyz/search"
UPLOAD_URL = "https://sci-net.xyz/upload"
UPSTREAM_URL = "https://sci-net.xyz/upstream"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.json")
PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf")

METADATA_KEYS = [
    "type",
    "title",
    "year",
    "journal",
    "authors",
    "topics",
    "abstract",
    "exception",
    "logo",
]


def apply_metadata(entry, result):
    """Copy the richer sci-net metadata into the paper entry."""
    for key in METADATA_KEYS:
        value = result.get(key)
        if value not in (None, ""):
            entry[key] = value
        else:
            entry.pop(key, None)


def query_scinet(doi, cookie):
    """POST to sci-net.xyz/search and return the response dict."""
    resp = requests.post(
        SCINET_URL,
        json={"doi": doi},
        headers={"content-type": "application/json"},
        cookies={"connect.sid": cookie},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def register_upload(doi, size, cookie):
    """POST to sci-net.xyz/upload and return the ticket."""
    resp = requests.post(
        UPLOAD_URL,
        json={"doi": doi, "size": size},
        headers={"content-type": "application/json"},
        cookies={"connect.sid": cookie},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("ticket", "")


def send_upstream(ticket, filename, pdf_path, cookie):
    """POST the PDF to sci-net.xyz/upstream with the ticket."""
    with open(pdf_path, "rb") as f:
        files = {"file": (filename, f, "application/pdf")}
        data = {"ticket": ticket}
        resp = requests.post(
            UPSTREAM_URL,
            data=data,
            files=files,
            cookies={"connect.sid": cookie},
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json().get("success", False)


def main():
    """Main function to query sci-net.xyz for each DOI in output.json."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cookie",
        default=os.environ.get("SCINET_COOKIE"),
        help="connect.sid cookie (or set SCINET_COOKIE in .env)",
    )
    parser.add_argument(
        "--only-query",
        action="store_true",
        help="Run Phase 4 only (query sci-net/sci-hub), then exit",
    )
    parser.add_argument(
        "--skip-query",
        action="store_true",
        help="Skip Phase 4, run Phases 6-7 (register + upload) only",
    )
    args = parser.parse_args()

    if not args.cookie:
        parser.error("Cookie is required. Pass --cookie or set SCINET_COOKIE in .env.")

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    total = len(data)

    if not args.skip_query:
        print("Phase 4: Querying sci-net.xyz ...")
        for i, entry in enumerate(data, 1):
            doi = entry.get("doi", "")
            if not doi:
                entry["sci_net"] = False
                entry["sci_hub"] = ""
                entry["status"] = "not-found"
                print(f"  {i}/{total} - skipped (no DOI)")
                continue

            retries = 3
            for attempt in range(retries):
                try:
                    result = query_scinet(doi, args.cookie)
                    entry["sci_net"] = bool(result.get("sci-net", False))
                    entry["sci_hub"] = result.get("sci-hub", "") or ""
                    apply_metadata(entry, result)
                    if entry["sci_net"]:
                        status = "sci-net"
                    elif entry["sci_hub"]:
                        status = "sci-hub"
                    else:
                        status = "not-found"
                    entry["status"] = status
                    print(f"  {i}/{total} - {doi} -> {status}")
                    break
                except requests.RequestException as exc:
                    if attempt < retries - 1:
                        print(f"  {i}/{total} - {doi} -> retry ({exc})")
                        time.sleep(2)
                    else:
                        entry["sci_net"] = False
                        entry["sci_hub"] = ""
                        entry["status"] = "not-found"
                        print(f"  {i}/{total} - {doi} -> failed ({exc})")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print("Phase 4 done.")

        if args.only_query:
            return

    print("Phase 6: Registering uploads ...")
    for i, entry in enumerate(data, 1):
        doi = entry.get("doi", "")
        number = entry.get("number", "")
        if entry.get("status") != "not-found":
            print(f"  {i}/{total} - skipped (status={entry.get('status')})")
            continue
        if not doi:
            entry["ticket"] = ""
            print(f"  {i}/{total} - skipped (no DOI)")
            continue

        pdf_path = os.path.join(PDF_DIR, f"{number}.pdf")
        try:
            size = os.path.getsize(pdf_path)
        except OSError:
            entry["ticket"] = ""
            print(f"  {i}/{total} - skipped (no pdf)")
            continue

        retries = 3
        for attempt in range(retries):
            try:
                ticket = register_upload(doi, size, args.cookie)
                entry["ticket"] = ticket
                print(f"  {i}/{total} - {doi} | size={size} -> ticket={ticket}")
                break
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    print(f"  {i}/{total} - {doi} -> retry ({exc})")
                    time.sleep(2)
                else:
                    entry["ticket"] = ""
                    print(f"  {i}/{total} - {doi} -> failed ({exc})")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Phase 6 done.")

    print("Phase 7: Uploading PDFs ...")
    for i, entry in enumerate(data, 1):
        doi = entry.get("doi", "")
        number = entry.get("number", "")
        ticket = entry.get("ticket", "")
        if not ticket:
            print(f"  {i}/{total} - skipped (no ticket)")
            continue

        pdf_path = os.path.join(PDF_DIR, f"{number}.pdf")
        if not os.path.exists(pdf_path):
            print(f"  {i}/{total} - skipped (no pdf)")
            continue

        filename = os.path.basename(pdf_path.replace("\\", "/"))
        retries = 3
        for attempt in range(retries):
            try:
                success = send_upstream(ticket, filename, pdf_path, args.cookie)
                entry["uploaded"] = success
                status = "uploaded" if success else "failed"
                print(f"  {i}/{total} - {doi} -> {status}")
                break
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    print(f"  {i}/{total} - {doi} -> retry ({exc})")
                    time.sleep(2)
                else:
                    entry["uploaded"] = False
                    print(f"  {i}/{total} - {doi} -> failed ({exc})")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Phase 7 done.")


if __name__ == "__main__":
    main()
