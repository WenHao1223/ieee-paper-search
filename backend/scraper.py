"""Search IEEE Xplore and extract title and document links from results."""

# uv run python run.py --query "deep learning" --pages-from 1 --pages-to 10 --cookie 'connect.sid=...'
# --query: The search query text to scrape IEEE Xplore for.
# --pages-from: The first page number to scrape (default 1).
# --pages-to: The last page number to scrape (default 10).
# --cookie (optional): The connect.sid cookie for sci-net.xyz (or set SCINET_COOKIE in .env).

import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import requests
from playwright.sync_api import sync_playwright

URL = "https://ieeexplore.ieee.org/rest/search"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "pdf")
PROFILE_DIR = os.path.join(BASE_DIR, "browser_profile")
HEADERS = {
    "content-type": "application/json",
    "referer": "https://ieeexplore.ieee.org/search/searchresult.jsp",
    "user-agent": "hi",
}


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


def main():
    """Fetch search results and write extracted fields to output.json."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--pages-from", type=int, default=1, help="First page to fetch (default 1)")
    parser.add_argument("--pages-to", type=int, default=10, help="Last page to fetch (default 10)")
    args = parser.parse_args()

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

    print("Phase 4: Downloading PDFs ...")
    os.makedirs(PDF_DIR, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            user_agent="hi",
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://ieeexplore.ieee.org/", wait_until="domcontentloaded", timeout=60000)
        page.bring_to_front()
        print(
            "  If not already logged in, sign in to IEEE in the opened window,"
            " then press Enter here."
        )
        input("  Press Enter when signed in ...")
        cookies = context.cookies()
        context.close()

    session_cookies = {c["name"]: c["value"] for c in cookies}

    jobs = []
    seen = set()
    for _, number, _, _ in rows:
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
    print("Phase 4 done.")


if __name__ == "__main__":
    main()
