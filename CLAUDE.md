# CLAUDE.md

Blueprint analyzes a GitHub repo (or local path) into an evidence-backed
architecture map: detected stack, entrypoints, review findings, a "start
here" guide, dependency graph, flow traces, and Mermaid/Markdown/HTML
export — every claim traces back to a real file, never invented.

## Tech Stack

- Python 3.12, stdlib-first (`git` CLI for cloning, `tomllib`/`ast`/`json`/`re`
  for parsing — no ORM/framework in `analyzer/`).
- `server/`: FastAPI + Uvicorn, static HTML/CSS/vanilla JS frontend
  (dagre.min.js vendored for graph layout, no build step).
- Lint/type-check: `ruff`, `ty`. Pre-commit + `detect-secrets`/Gitleaks.

## Commands

```
# install
pip install -r server/requirements.txt
pip install pytest httpx ruff ty   # dev/test-only, not pinned in a requirements file

# run web app (from repo root, then open 127.0.0.1:8000)
uvicorn server.main:app --reload --app-dir .

# run CLI (Markdown report to stdout)
python3 analyzer/cli.py <github-repo-url>

# test
python -m pytest analyzer server -q

# lint / type-check
ruff check analyzer server
ty check --output-format concise
```

## Architecture

- `analyzer/analyze.py` — core pipeline: clone/scan a repo into a
  `RepoIndex` (files, manifests, roles, `Finding`s, `Module`s, graph
  `Node`/`Edge`s, `Flow`s, `Subsystem` clusters). Every derived fact cites
  a real file path; all other layers import from here, no duplicated logic.
- `analyzer/report.py`, `mermaid.py`, `html_export.py` — render a
  `RepoIndex` into Markdown, Mermaid, and self-contained HTML.
- `analyzer/cli.py` — thin CLI wrapper.
- `server/main.py` — FastAPI wrapper: `POST /api/analyze` calls
  `analyzer.analyze_github_repo` directly; `/api/export/{markdown,mermaid,html}`
  re-render the same JSON, no re-analysis.
- `server/static/` — single-page frontend (`app.js` report view,
  `graph.js` architecture graph, `flow.js` flow explorer, `export.js`
  copy/download), tabbed, dark "blueprint" theme.
- `.claude/skills/understand-repo/` — separate skill: sweeps a *local*
  repo path, clusters subsystems, layers verified (claim +
  independent-refutation) AI summaries. Writes to `.understanding/`
  (gitignored, never committed).

## Key Docs

- `docs/prd.md` — product spec and MVP scope.
- `docs/issues.md` — slice-by-slice implementation plan.
- `docs/HANDOFF.md` — per-slice passdown log; read before new work.
