# Blueprint Server (Slice 5)

FastAPI wrapper around the `analyzer/` pipeline: one endpoint
(`POST /api/analyze`) plus a static single-page frontend that calls it.
No analysis or Markdown-rendering logic lives here — `server/main.py`
imports and calls `analyzer/analyze.py`'s `analyze_github_repo` directly.

## Setup

From the repo root:

```
pip install -r server/requirements.txt
```

(Testing the API also needs `httpx`/`pytest`, same as `analyzer/`'s tests —
not pinned in `requirements.txt` since they're dev-only, mirroring how
`analyzer/`'s CI installs `pytest`/`ruff`/`ty` directly rather than via a
requirements file.)

## Run

From the repo root:

```
uvicorn server.main:app --reload --app-dir .
```

Then open `http://127.0.0.1:8000/` in a browser, or hit the API directly:

```
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/octocat/Hello-World"}'
```

A bad/private/unreachable URL returns a 400 with `{"error": "..."}"`,
never a raw traceback.

## Tests

```
python -m pytest server -q
```
