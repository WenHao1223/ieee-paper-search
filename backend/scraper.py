"""Search IEEE Xplore and extract title and document links from results."""

import argparse
import json
import urllib.request

URL = "https://ieeexplore.ieee.org/rest/search"
HEADERS = {
    "content-type": "application/json",
    "referer": "https://ieeexplore.ieee.org/search/searchresult.jsp",
    "user-agent": "hi",
}


def fetch_records(query):
    """Return the JSON search response for the given query."""
    payload = {"queryText": query}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def extract_fields(records):
    """Build a list of (title, link) tuples from the given records."""
    out = []
    for rec in records:
        title = rec.get("highlightedTitle", "")
        link = "https://ieeexplore.ieee.org" + rec.get("documentLink", "")
        out.append((title, link))
    return out


def main():
    """Fetch search results and write extracted fields to output.json."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Search query text")
    args = parser.parse_args()
    result = fetch_records(args.query)
    rows = extract_fields(result.get("records", []))
    data = [{"title": title, "link": link} for title, link in rows]
    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
