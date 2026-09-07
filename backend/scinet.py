"""Query sci-net.xyz to check which DOIs have been uploaded."""

# uv run python scinet.py --cookie 'connect.sid=...'

import argparse
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()


SCINET_URL = "https://sci-net.xyz/search"
UPLOAD_URL = "https://sci-net.xyz/upload"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.json")
PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf")


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


def main():
    """Main function to query sci-net.xyz for each DOI in output.json."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cookie",
        default=os.environ.get("SCINET_COOKIE"),
        help="connect.sid cookie (or set SCINET_COOKIE in .env)",
    )
    args = parser.parse_args()

    if not args.cookie:
        parser.error("Cookie is required. Pass --cookie or set SCINET_COOKIE in .env.")

    print("Phase 5: Querying sci-net.xyz ...")
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = len(data)
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
                entry["sci_hub"] = result.get("sci-hub", "")
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

    print("Phase 5 done.")

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


if __name__ == "__main__":
    main()
