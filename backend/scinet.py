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
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.json")


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
            print(f"  {i}/{total} - skipped (no DOI)")
            continue

        retries = 3
        for attempt in range(retries):
            try:
                result = query_scinet(doi, args.cookie)
                entry["sci_net"] = bool(result.get("sci-net", False))
                status = "found" if entry["sci_net"] else "not found"
                print(f"  {i}/{total} - {doi} -> {status}")
                break
            except requests.RequestException as exc:
                if attempt < retries - 1:
                    print(f"  {i}/{total} - {doi} -> retry ({exc})")
                    time.sleep(2)
                else:
                    entry["sci_net"] = False
                    print(f"  {i}/{total} - {doi} -> failed ({exc})")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Phase 5 done.")


if __name__ == "__main__":
    main()
