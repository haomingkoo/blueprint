"""Read-only bridge: if a local understand-repo sweep already exists for
the analyzed repo (matched by name), merge its verified data into the
`/api/analyze` response. Never triggers a sweep, never writes to the
sweep db -- see
docs/superpowers/specs/2026-07-06-web-graph-understanding-bridge-design.md
for the full design. Any failure (no sweep, corrupt db, missing table)
leaves the response untouched -- this is enrichment, never a hard
dependency of the analyze endpoint.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UNDERSTANDING_ROOT = REPO_ROOT / ".understanding"
_SKILL_SCRIPTS_DIR = REPO_ROOT / ".claude" / "skills" / "understand-repo" / "scripts"
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))


def enrich_with_understanding(repo_name: str, response: dict) -> dict:
    """Mutates and returns `response` (the dict `asdict(index)` produced)
    with optional verified fields merged in, if a sweep's `latest`
    directory exists for `repo_name`."""
    db_path = UNDERSTANDING_ROOT / repo_name / "latest" / "understanding.db"
    if not db_path.exists():
        return response

    try:
        from edges import load_edges_with_descriptions  # noqa: PLC0415 (only resolvable once scripts dir is on sys.path)

        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT overview, commit_sha FROM sweeps LIMIT 1").fetchone()
            if row is None:
                return response
            overview, commit_sha = row
            summaries = {
                module_name: {"text": text, "evidence_files": json.loads(evidence_files)}
                for module_name, text, evidence_files in conn.execute(
                    "SELECT module_name, summary_text, evidence_files FROM semantic_summaries"
                )
            }
        finally:
            conn.close()
        described_edges = load_edges_with_descriptions(db_path)
    except (sqlite3.Error, KeyError, ImportError):
        return response

    if overview:
        response["understanding_overview"] = overview
    if commit_sha:
        response["understanding_commit_sha"] = commit_sha

    for node in response.get("nodes", []):
        module_name = node["id"].removeprefix("module:")
        if module_name in summaries:
            node["verified_summary"] = summaries[module_name]

    description_by_pair = {
        (e["source"], e["target"]): e["description"] for e in described_edges if "description" in e
    }
    for edge in response.get("edges", []):
        key = (edge["source"], edge["target"])
        if key in description_by_pair:
            edge["verified_description"] = description_by_pair[key]

    return response
