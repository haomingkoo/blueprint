# CLAUDE.md

Blueprint turns a GitHub repo or local path into an evidence-backed architecture map. Every derived claim must cite a real file; never invent one.

## Commands

```bash
pip install -r server/requirements.txt
pip install pytest httpx ruff==0.15.20 ty==0.0.56     # dev tools; versions match CI
uvicorn server.main:app --reload --app-dir .           # web app on 127.0.0.1:8000
python3 analyzer/cli.py <github-repo-url>              # Markdown report to stdout
python -m pytest analyzer server -q
ruff check analyzer server && ty check --output-format concise
```

## Constraints

- `analyzer/` is stdlib-only (plus the `git` CLI). No frameworks there.
- `analyzer/analyze.py` owns all analysis; renderers and `server/` import from it rather than re-deriving. Export endpoints re-render the same JSON without re-analysing.
- Frontend is static vanilla JS with vendored `dagre.min.js`; no build step.
- The `understand-repo` skill writes to `.understanding/`, which is gitignored. Never commit it.
- Read `docs/HANDOFF.md` before starting new work.
