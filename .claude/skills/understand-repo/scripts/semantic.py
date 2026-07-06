#!/usr/bin/env python3
"""understand-repo Slice 11: persist and render verified per-module
semantic summaries.

The actual verification (Agent A writes a claim citing evidence files,
Agent B independently re-reads the same files and tries to refute it) is
judgment, not code -- it's carried out by whoever is running the skill,
following SKILL.md's semantic-phase instructions. This script only handles
the deterministic half: writing a claim that survived refutation into the
sweep's SQLite DB, and rendering every module (verified or not) into
report.md. A module with no verified row gets an explicit "not verified"
note -- it is never silently dropped.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from db import open_db


def add_semantic_summary(db_path: Path, module_name: str, summary_text: str, evidence_files: list[str]) -> None:
    with open_db(db_path) as conn:
        sweep_id = conn.execute("SELECT id FROM sweeps LIMIT 1").fetchone()[0]
        # OR REPLACE: re-adding a claim for a module (e.g. corrected after
        # an earlier attempt) deterministically replaces it, rather than
        # leaving two rows whose read order is an unordered-scan artifact.
        conn.execute(
            "INSERT OR REPLACE INTO semantic_summaries "
            "(sweep_id, module_name, summary_text, evidence_files, verified, confidence) "
            "VALUES (?, ?, ?, ?, 1, 'semantic')",
            (sweep_id, module_name, summary_text, json.dumps(evidence_files)),
        )
        conn.commit()


def render_semantic_report(db_path: Path) -> str:
    with open_db(db_path) as conn:
        module_names = sorted({
            row[0] for row in conn.execute("SELECT DISTINCT module_name FROM module_subsystem")
        })
        verified = {
            row[0]: (row[1], json.loads(row[2]))
            for row in conn.execute(
                "SELECT module_name, summary_text, evidence_files FROM semantic_summaries"
            )
        }

    lines = ["# AI Interpretation — verified", ""]
    for name in module_names:
        lines.append(f"## {name}")
        lines.append("")
        if name in verified:
            summary_text, evidence_files = verified[name]
            lines.append(summary_text)
            lines.append("")
            lines.append(f"**Evidence:** {', '.join(evidence_files)}")
        else:
            lines.append(
                "_No verified semantic summary this sweep — every claim was refuted, "
                "or the agent call failed._"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """The `add` command takes a JSON payload file, not inline text/filename
    arguments: `summary_text` is LLM-written and `evidence_files` are real
    paths from the (possibly untrusted) swept repo, so neither is safe to
    interpolate into a shell command line. A payload file sidesteps shell
    quoting entirely -- only two agent-controlled paths (sweep_dir, payload)
    ever appear on the command line."""
    parser = argparse.ArgumentParser(description="Persist and render verified per-module semantic summaries")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Persist one verified summary from a JSON payload file")
    add_parser.add_argument("sweep_dir")
    add_parser.add_argument(
        "payload",
        help='Path to a JSON file: {"module_name": "...", "summary_text": "...", "evidence_files": ["..."]}',
    )

    report_parser = subparsers.add_parser("report", help="Render report.md for a sweep")
    report_parser.add_argument("sweep_dir")

    args = parser.parse_args()
    db_path = Path(args.sweep_dir) / "understanding.db"

    if args.command == "add":
        payload = json.loads(Path(args.payload).read_text())
        add_semantic_summary(db_path, payload["module_name"], payload["summary_text"], payload["evidence_files"])
        print(f"Persisted verified summary for module '{payload['module_name']}'")
    else:
        report_path = Path(args.sweep_dir) / "report.md"
        report_path.write_text(render_semantic_report(db_path))
        print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
