#!/usr/bin/env python3
"""understand-repo Slice 14: verified per-edge semantic descriptions.

Same pattern as Slice 11 (semantic.py), applied to edges instead of
modules: Agent A reads the real evidence files and writes one concrete
sentence about what a specific "imports" edge actually does (not just
"module A imports module B", but e.g. "calls formatHeaders() from utils to
build the request"); Agent B -- fresh context, no visibility into Agent
A's reasoning -- tries to refute it. Only unrefuted claims are persisted.
An edge with no verified description simply falls back to its existing
static label ("imports"/"depends on") -- never silently replaced with an
unverified guess.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def add_edge_description(
    db_path: Path, source: str, target: str, description: str, evidence_files: list[str]
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        sweep_id = conn.execute("SELECT id FROM sweeps LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO edge_descriptions (sweep_id, source, target, description, evidence_files, confidence) "
            "VALUES (?, ?, ?, ?, ?, 'semantic')",
            (sweep_id, source, target, description, json.dumps(evidence_files)),
        )
        conn.commit()
    finally:
        conn.close()


def load_edges_with_descriptions(db_path: Path) -> list[dict]:
    """Every real edge, each paired with its verified description if one
    survived this sweep -- used by report/site renderers so a described
    edge shows its sentence and an undescribed one shows its plain label,
    never the other way around."""
    conn = sqlite3.connect(db_path)
    try:
        edge_rows = conn.execute("SELECT source, target, type, label FROM edges").fetchall()
        description_rows = conn.execute(
            "SELECT source, target, description, evidence_files FROM edge_descriptions"
        ).fetchall()
    finally:
        conn.close()

    descriptions = {(s, t): (desc, json.loads(ev)) for s, t, desc, ev in description_rows}
    result = []
    for source, target, edge_type, label in edge_rows:
        entry = {"source": source, "target": target, "type": edge_type, "label": label}
        if (source, target) in descriptions:
            entry["description"], entry["evidence_files"] = descriptions[(source, target)]
        result.append(entry)
    return result


def render_edge_descriptions_report(db_path: Path) -> str:
    """Verified per-edge descriptions only -- an undescribed edge has
    nothing new to say here (it's just the plain structural fact already
    implied by the subsystem graph), so this section lists only edges that
    survived Phase 4's independent refutation check this sweep."""
    described = [e for e in load_edges_with_descriptions(db_path) if "description" in e]
    lines = ["# Edge Descriptions — verified", ""]
    if not described:
        lines.append("_No verified edge descriptions this sweep._")
        lines.append("")
        return "\n".join(lines)
    for e in described:
        source = e["source"].removeprefix("module:").removeprefix("manifest:")
        target = e["target"].removeprefix("module:").removeprefix("manifest:")
        lines.append(f"- **{source} → {target}:** {e['description']}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """The `add` command takes a JSON payload file, not inline text/filename
    arguments: `description` is LLM-written and `evidence_files` are real
    paths from the (possibly untrusted) swept repo, so neither is safe to
    interpolate into a shell command line. A payload file sidesteps shell
    quoting entirely -- only two agent-controlled paths (sweep_dir, payload)
    ever appear on the command line."""
    parser = argparse.ArgumentParser(description="Persist a verified per-edge semantic description")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Persist one verified edge description from a JSON payload file")
    add_parser.add_argument("sweep_dir")
    add_parser.add_argument(
        "payload",
        help='Path to a JSON file: {"source": "...", "target": "...", "description": "...", "evidence_files": ["..."]}',
    )

    list_parser = subparsers.add_parser("list", help="Print every edge and its description, if any")
    list_parser.add_argument("sweep_dir")

    args = parser.parse_args()
    db_path = Path(args.sweep_dir) / "understanding.db"

    if args.command == "add":
        payload = json.loads(Path(args.payload).read_text())
        add_edge_description(
            db_path, payload["source"], payload["target"], payload["description"], payload["evidence_files"]
        )
        print(f"Persisted description for {payload['source']} -> {payload['target']}")
    else:
        for e in load_edges_with_descriptions(db_path):
            if "description" in e:
                print(f"{e['source']} -> {e['target']}: {e['description']}")
            else:
                print(f"{e['source']} -> {e['target']}: ({e['label']}, not described this sweep)")


if __name__ == "__main__":
    main()
