# Blueprint

Blueprint turns a public GitHub repository into an evidence-backed architecture
map: modules, dependencies, likely execution flows, risks, and reviewable
Markdown, Mermaid, or standalone HTML reports.

It favours explicit uncertainty over confident-looking guesses. Import edges are
derived with lightweight static analysis and labelled as heuristic where a full
language resolver is not available.

## What it produces

- Repository and module inventory
- Dependency and architecture graphs
- Traced execution flows through the graph
- Evidence-linked findings and risk flags
- Markdown, Mermaid, and offline HTML exports
- A FastAPI endpoint and browser interface for public repositories

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
uvicorn server.main:app --reload
```

Run the analyzer tests from the repository root:

```bash
python -m pytest analyzer server
```

The product contract and design rationale live in [`docs/`](docs/).
