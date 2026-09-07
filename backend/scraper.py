"""Search IEEE Xplore and extract title and document links from results."""

# python scraper.py --query "deep learning"

import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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


def fetch_records(query):
    """Return the JSON search response for the given query."""
    payload = {"queryText": query}
    resp = requests.post(URL, json=payload, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def download_pdf(session_cookies, article_number, target, counter, total):
    """Download one article PDF using the signed-in session cookies.

    Returns True on success, False when access is locked or the fetch fails.
    """
    pdf_url = "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=" + article_number
    try:
        resp = requests.get(pdf_url, cookies=session_cookies, timeout=60, headers={"user-agent": "hi"})
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
    except Exception as exc:
        print(f"  Failed {article_number}: {exc}")
        return False


def extract_fields(records):
    """Build a list of (title, number, link) tuples from the given records."""
    out = []
    for rec in records:
        title = rec.get("highlightedTitle", "")
        number = rec.get("articleNumber", "")
        link = "https://ieeexplore.ieee.org" + rec.get("documentLink", "")
        out.append((title, number, link))
    return out


def main():
    """Fetch search results and write extracted fields to output.json."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Search query text")
    args = parser.parse_args()

    print(f"Phase 1: Fetching records for query '{args.query}' ...")
    result = fetch_records(args.query)
    print("Phase 1 done.")

    print("Phase 2: Extracting fields ...")
    rows = extract_fields(result.get("records", []))
    print("Phase 2 done.")

    print("Phase 3: Writing output.json ...")
    data = [{"title": title, "number": number, "link": link} for title, number, link in rows]
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
        print("  If not already logged in, sign in to IEEE in the opened window, then press Enter here.")
        input("  Press Enter when signed in ...")
        cookies = context.cookies()
        context.close()

    session_cookies = {c["name"]: c["value"] for c in cookies}

    pending = []
    for _, number, _ in rows:
        if not number:
            continue
        target = os.path.join(PDF_DIR, f"{number}.pdf")
        if os.path.exists(target) and os.path.getsize(target) > 0:
            continue
        if os.path.exists(target):
            os.remove(target)
        pending.append((number, target))

    counter = {"n": 0, "lock": threading.Lock()}
    total = len(pending)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(download_pdf, session_cookies, number, target, counter, total): number
            for number, target in pending
        }
        for future in as_completed(futures):
            future.result()
    print("Phase 4 done.")


if __name__ == "__main__":
    main()
