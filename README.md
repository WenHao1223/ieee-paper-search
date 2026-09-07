# scrap-ieee

Search IEEE Xplore for academic papers, download their PDFs, and automatically upload papers not found on sci-net.xyz or sci-hub. All backend scripts live in the `backend/` folder.

## How It Works

The tool runs 7 sequential phases:

1. **Phase 1** - Query the IEEE Xplore search API across multiple pages
2. **Phase 2** - Extract title, article number, link, and DOI from results
3. **Phase 3** - Write extracted data to `output.json`
4. **Phase 4** - Query sci-net.xyz and sci-hub to check DOI availability
5. **Phase 5** - Open a browser for IEEE login, then download PDFs only for papers not found on sci-net/sci-hub
6. **Phase 6** - Register upload tickets for papers not found anywhere
7. **Phase 7** - Upload PDFs to sci-net.xyz

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+ (for the frontend)

## Running the Web App

The web app is split into a FastAPI **backend** and a React **frontend**. Start the backend first, then the frontend.

### 1. Start the backend (API)

```bash
cd backend
uv run python server.py
```

- Serves the API on `http://localhost:8000`.
- Make sure `SCINET_COOKIE` is set (see Environment Setup) so the pipeline can check sci-net and upload PDFs.
- To change the port, set the `PORT` env var (e.g. `PORT=9000`).
- **IEEE sign-in:** the download step opens a browser to sign you into IEEE when the saved session is stale. Override the wait with the `LOGIN_WAIT` env var (seconds).

### 2. Start the frontend (UI)

```bash
cd frontend
npm install
npm run dev
```

- Opens the web UI at `http://localhost:5173` (Vite dev server).
- By default it calls the backend at the same host. If the API is on a different host/port, set the API base in `frontend/.env`:

```text
VITE_API_BASE=http://localhost:8000
```

### API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/search` | Start a search job `{"query": string, "count": 1-250}` → `{"id"}` |
| `GET` | `/api/jobs/{id}` | Live status, phase, log tail and results for a job |
| `GET` | `/api/jobs` | Summary of all jobs |
| `GET` | `/api/results` | Current results from `output.json` |
| `GET` | `/api/refresh` | Re-query sci-net for papers still `not-found` (e.g. after uploads propagate) |

## Environment Setup

### 1. Install dependencies

```bash
cd backend
uv sync
```

### 2. Install Playwright browsers

```bash
uv run playwright install chromium
```

### 3. Configure environment variables

Copy the example env file and fill in your sci-net.xyz session cookie:

```bash
cp .env.example .env
```

Edit `.env`:

```text
SCINET_COOKIE=your_connect.sid_cookie_value_here
```

The cookie can also be passed via the `--cookie` CLI flag instead.

## Usage

All commands run from inside the `backend/` directory.

### Run the full pipeline

```bash
uv run python run.py --query "search term" --pages-from 1 --pages-to 10
```

This runs Phase 1-3 (scrape), Phase 4 (sci-net/sci-hub lookup), Phase 5 (download missing PDFs), and Phases 6-7 (register and upload).

> **IEEE sign-in:** Phase 5 opens a browser window. If the saved IEEE session is still valid it proceeds immediately; otherwise it waits for you to sign in (default `--login-wait 180s`, override with the `LOGIN_WAIT` env var for the server). This works for both `run.py` and the server.

### Run individual scripts

**Scraper only** (Phases 1-3, plus Phase 5 with `--download-missing`):

```bash
uv run python scraper.py --query "search term" --pages-from 1 --pages-to 10
uv run python scraper.py --download-missing
```

**Sci-net lookup and upload only** (Phases 4-7):

```bash
uv run python scinet.py --cookie 'connect.sid=...'
```

Or run individual stages:

```bash
uv run python scinet.py --cookie 'connect.sid=...' --only-query   # Phase 4
uv run python scinet.py --cookie 'connect.sid=...' --skip-query   # Phases 6-7
```

## CLI Arguments

### `run.py`

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `--query` | Yes | - | Search query text for IEEE Xplore |
| `--pages-from` | No | `1` | First page number to scrape |
| `--pages-to` | No | `10` | Last page number to scrape |
| `--cookie` | No | `SCINET_COOKIE` env var | `connect.sid` cookie for sci-net.xyz |

### `scraper.py`

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `--query` | Yes* | - | Search query text (*not needed with `--download-missing`) |
| `--pages-from` | No | `1` | First page to fetch |
| `--pages-to` | No | `10` | Last page to fetch |
| `--download-missing` | No | - | Phase 5: download PDFs only for papers not found on sci-net/sci-hub |
| `--non-interactive` | No | - | Reuse the saved browser profile in headless mode (fails fast if not signed in) |
| `--login-wait` | No | `180` | Seconds to wait for interactive IEEE sign-in in the opened browser |

### `scinet.py`

| Argument | Required | Default | Description |
| --- | --- | --- | --- |
| `--cookie` | No | `SCINET_COOKIE` env var | `connect.sid` cookie (required at runtime) |
| `--only-query` | No | - | Run Phase 4 only (query sci-net/sci-hub), then exit |
| `--skip-query` | No | - | Skip Phase 4, run Phases 6-7 (register + upload) only |

## Output

### `output.json`

Generated by the scraper and enriched by scinet.py. Each entry contains:

```json
{
  "title": "Paper Title",
  "number": "12345678",
  "link": "https://ieeexplore.ieee.org/document/12345678",
  "doi": "10.1109/EXAMPLE.2024.12345678",
  "sci_net": true,
  "sci_hub": "https://sci-hub.se/10.1109/EXAMPLE.2024.12345678",
  "status": "sci-net",
  "ticket": "",
  "uploaded": false
}
```

**Status values:** `sci-net` | `sci-hub` | `not-found`

### `pdf/`

Downloaded PDFs are saved as `pdf/<article_number>.pdf`.

### `browser_profile/`

Persistent Chromium profile that stores your IEEE Xplore login session so you don't have to re-authenticate every run.

## Project Structure

```text
.
├── backend/             # All backend code
│   ├── run.py           # Orchestrator - runs scraper (Phases 1-3, 5) and scinet (Phases 4, 6-7)
│   ├── server.py        # FastAPI web API (start with: uv run python server.py)
│   ├── scraper.py       # Phases 1-3: search IEEE, write JSON; Phase 5: download missing PDFs
│   ├── scinet.py        # Phase 4: query sci-net/sci-hub; Phases 6-7: register + upload
│   ├── pyproject.toml   # Dependencies and project config
│   ├── .env             # Environment variables (gitignored)
│   ├── .env.example     # Env template
│   ├── output.json      # Generated search results
│   ├── pdf/             # Downloaded PDFs
│   └── browser_profile/ # Chromium login session
└── frontend/            # React frontend (start with: npm run dev)
    ├── src/             # App, PaperCard, api and types
    ├── index.html
    └── package.json
```
