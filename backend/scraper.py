"""Search IEEE Xplore and extract title and document links from results."""

# uv run python run.py --query "deep learning" --pages-from 1 --pages-to 10 --cookie 'connect.sid=...'
# --query: The search query text to scrape IEEE Xplore for.
# --pages-from: The first page number to scrape (default 1).
# --pages-to: The last page number to scrape (default 10).
# --download-missing (optional): Phase 5 – download PDFs only for papers not found on sci-net/sci-hub.
# --non-interactive (optional): Reuse the saved browser profile in headless mode without prompting for login.
# --cookie (optional): The connect.sid cookie for sci-net.xyz (or set SCINET_COOKIE in .env).

import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import requests
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

URL = "https://ieeexplore.ieee.org/rest/search"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "pdf")
PROFILE_DIR = os.path.join(BASE_DIR, "browser_profile")
SIGN_IN_SELECTOR = ".stats-Unav_P_SignIn"
HEADERS = {
    "content-type": "application/json",
    "referer": "https://ieeexplore.ieee.org/search/searchresult.jsp",
    "user-agent": "hi",
}

LOGIN_WAIT_DEFAULT = 180


def fetch_records(query, page_number=1):
    """Return the JSON search response for the given query and page."""
    payload = {"queryText": query, "pageNumber": str(page_number)}
    resp = requests.post(URL, json=payload, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def download_pdf(session_cookies, article_number, target, counter, total):
    """Download one article PDF using the signed-in session cookies.

    Returns True on success, False when access is locked or the fetch fails.
    """
    pdf_url = "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=" + article_number
    try:
        resp = requests.get(
            pdf_url,
            cookies=session_cookies,
            timeout=60,
            headers={"user-agent": "hi"}
        )
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            print(f"  Skipped {article_number}: PDF not accessible (locked?)")
            return False
        with open(target, "wb") as f:
            f.write(resp.content)
        with counter["lock"]:
            counter["n"] += 1
            progress = counter["n"]
        print(f"  Saved {progress}/{total} - {article_number}.pdf")
        return True
    except (OSError, requests.RequestException) as exc:
        print(f"  Failed {article_number}: {exc}")
        return False


def skip_pdf(article_number, counter, total, reason):
    """Count a skipped article number toward progress."""
    with counter["lock"]:
        counter["n"] += 1
        progress = counter["n"]
    print(f"  Saved {progress}/{total} - {article_number}.pdf (skipped: {reason})")


def extract_fields(records):
    """Build a list of (title, number, link, doi) tuples from the given records."""
    out = []
    for rec in records:
        title = rec.get("highlightedTitle", "")
        number = rec.get("articleNumber", "")
        doi = rec.get("doi", "")
        link = "https://ieeexplore.ieee.org" + rec.get("documentLink", "")
        out.append((title, number, link, doi))
    return out


def merge_rows(rows):
    """Merge rows across pages, keeping unique article numbers in order."""
    merged = []
    seen = set()
    for item in rows:
        if item[1] in seen:
            continue
        seen.add(item[1])
        merged.append(item)
    return merged


def download_missing(args):
    """Phase 5: download PDFs only for papers not found on sci-net/sci-hub.

    Reads output.json and downloads PDFs for entries whose status is
    "not-found", "not-checked" or unset (not-checked/unset mean Phase 4 was
    skipped, so download all).
    """
    print("Phase 5: Downloading missing PDFs ...")
    os.makedirs(PDF_DIR, exist_ok=True)

    with open("output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    missing = [
        entry for entry in data
        if entry.get("status") in ("not-found", "not-checked", "")
        or not entry.get("status")
    ]
    if not missing:
        print("  No missing PDFs to download.")
        print("Phase 5 done.")
        return

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=args.non_interactive,
            user_agent="hi",
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://ieeexplore.ieee.org/", wait_until="domcontentloaded", timeout=60000)
        page.bring_to_front()
        signed_in = page.locator(SIGN_IN_SELECTOR).count() == 0

        if args.non_interactive:
            if not signed_in:
                context.close()
                print("  IEEE session not signed in (saved browser profile expired).")
                print("  Run interactively once to refresh it: uv run python scraper.py --download-missing")
                raise SystemExit(1)
            print("  Using saved browser profile (non-interactive, headless).")
        elif not signed_in:
            print(
                "  IEEE is not signed in. Sign in to IEEE in the opened window"
                f" (waiting up to {args.login_wait}s) ..."
            )
            try:
                page.wait_for_function(
                    f"() => document.querySelector('{SIGN_IN_SELECTOR}') === null",
                    timeout=args.login_wait * 1000,
                )
            except PlaywrightTimeoutError:
                context.close()
                print("  Timed out waiting for IEEE sign-in.")
                raise SystemExit(1)
        cookies = context.cookies()
        context.close()

    session_cookies = {c["name"]: c["value"] for c in cookies}

    jobs = []
    seen = set()
    for entry in missing:
        number = entry.get("number", "")
        if not number:
            continue
        if number in seen:
            jobs.append((number, None))
            continue
        seen.add(number)
        target = os.path.join(PDF_DIR, f"{number}.pdf")
        if os.path.exists(target) and os.path.getsize(target) > 0:
            jobs.append((number, None))
            continue
        if os.path.exists(target):
            os.remove(target)
        jobs.append((number, target))

    counter = {"n": 0, "lock": threading.Lock()}
    total = len(jobs)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for number, target in jobs:
            if target is None:
                futures.append((
                    number,
                    executor.submit(
                        skip_pdf, number, counter, total,
                        "duplicate or already exists",
                    ),
                ))
            else:
                futures.append((
                    number,
                    executor.submit(
                        download_pdf, session_cookies, number, target,
                        counter, total,
                    ),
                ))
        for _, future in futures:
            future.result()
    print("Phase 5 done.")


def main():
    """Fetch search results and write extracted fields to output.json."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", help="Search query text (required unless --download-missing)")
    parser.add_argument("--pages-from", type=int, default=1, help="First page to fetch (default 1)")
    parser.add_argument("--pages-to", type=int, default=10, help="Last page to fetch (default 10)")
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="Phase 5: download PDFs only for papers not found on sci-net/sci-hub",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Reuse the saved browser profile in headless mode without prompting for login",
    )
    parser.add_argument(
        "--login-wait",
        type=int,
        default=LOGIN_WAIT_DEFAULT,
        help=f"Seconds to wait for interactive IEEE sign-in (default {LOGIN_WAIT_DEFAULT})",
    )
    args = parser.parse_args()

    if args.download_missing:
        download_missing(args)
        return

    if not args.query:
        parser.error("--query is required unless --download-missing is given.")

    print(f"Phase 1: Fetching records for query '{args.query}' ...")
    all_rows = []
    pages = range(args.pages_from, args.pages_to + 1)
    for page_number in pages:
        print(f"  Fetching page {page_number}/{args.pages_to} ...")
        result = fetch_records(args.query, page_number)
        all_rows.extend(extract_fields(result.get("records", [])))
    print("Phase 1 done.")

    print("Phase 2: Extracting fields ...")
    rows = merge_rows(all_rows)
    print(f"Phase 2 done ({len(rows)} unique records).")

    print("Phase 3: Writing output.json ...")
    data = [
        {
            "title": title,
            "number": number,
            "link": link,
            "doi": doi
        }
        for title, number, link, doi in rows
    ]
    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Phase 3 done.")


if __name__ == "__main__":
    main()
