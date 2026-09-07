"""Run scraper.py and scinet.py sequentially with shared arguments."""

# uv run python run.py --query "deep learning" --pages-from 1 --pages-to 10 --cookie 'connect.sid=...'
# --query: The search query text to scrape IEEE Xplore for.
# --pages-from: The first page number to scrape (default 1).
# --pages-to: The last page number to scrape (default 10).
# --cookie (optional): The connect.sid cookie for sci-net.xyz (or set SCINET_COOKIE in .env).

import argparse
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run(script, args):
    """Run a child script with the given args list. Exit on failure."""
    cmd = [sys.executable, os.path.join(BASE_DIR, script)] + args
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Query sci-net availability, download missing PDFs, then upload.")
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--pages-from", type=int, default=1, help="First page (default 1)")
    parser.add_argument("--pages-to", type=int, default=10, help="Last page (default 10)")
    parser.add_argument(
        "--cookie",
        default=os.environ.get("SCINET_COOKIE"),
        help="connect.sid cookie for sci-net (or set SCINET_COOKIE in .env)",
    )
    args = parser.parse_args()

    scraper_args = ["--query", args.query, "--pages-from", str(args.pages_from), "--pages-to", str(args.pages_to)]

    run("scraper.py", scraper_args)
    if args.cookie:
        run("scinet.py", ["--cookie", args.cookie, "--only-query"])
        run("scraper.py", scraper_args + ["--download-missing"])
        run("scinet.py", ["--cookie", args.cookie, "--skip-query"])
    else:
        print("Skipping Phase 4: no --cookie provided (querying sci-net/sci-hub).")
        run("scraper.py", scraper_args + ["--download-missing"])
        print("Skipping Phases 6-7: no --cookie provided.")


if __name__ == "__main__":
    main()
