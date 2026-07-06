#!/usr/bin/env python3
"""understand-repo Slice 12: subsystem synthesis narrative.

Like Slice 11, the actual writing is judgment (one agent, given only the
verified per-module summaries + cluster assignments + real depends_on
edges, names each subsystem and narrates how it fits into the repo) --
carried out per SKILL.md's Phase 3 instructions. This script only handles
the deterministic half: persisting a subsystem's name/narrative or the
sweep's overview, and rendering the full report.md (overview + subsystems
+ the existing per-module section from Slice 11).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from edges import render_edge_descriptions_report
from semantic import render_semantic_report


def update_subsystem(db_path: Path, subsystem_id: str, name: str, narrative: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE subsystems SET name = ?, narrative = ? WHERE id = ?",
            (name, narrative, subsystem_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_sweep_overview(db_path: Path, overview: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE sweeps SET overview = ?", (overview,))
        conn.commit()
    finally:
        conn.close()


def render_full_report(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        repo_name, overview = conn.execute("SELECT repo_name, overview FROM sweeps LIMIT 1").fetchone()
        subsystem_rows = conn.execute(
            "SELECT id, name, narrative FROM subsystems ORDER BY name"
        ).fetchall()
        module_rows = conn.execute("SELECT subsystem_id, module_name FROM module_subsystem").fetchall()
    finally:
        conn.close()

    modules_by_subsystem: dict[str, list[str]] = {}
    for subsystem_id, module_name in module_rows:
        modules_by_subsystem.setdefault(subsystem_id, []).append(module_name)

    lines = [f"# {repo_name} — Understanding Report", ""]
    lines.append(overview if overview else "_No synthesis overview yet — run the Slice 12 synthesis phase._")
    lines.append("")
    lines.append("## Subsystems")
    lines.append("")
    for subsystem_id, name, narrative in subsystem_rows:
        lines.append(f"### {name}")
        lines.append("")
        lines.append(narrative if narrative else "_No synthesized narrative yet for this subsystem._")
        lines.append("")
        members = sorted(modules_by_subsystem.get(subsystem_id, []))
        lines.append(f"**Modules:** {', '.join(members)}")
        lines.append("")

    lines.append(render_semantic_report(db_path))
    lines.append(render_edge_descriptions_report(db_path))
    return "\n".join(lines)


def main() -> None:
    """`update-subsystem`/`set-overview` take a JSON payload file, not inline
    text arguments: `name`/`narrative`/`overview` are all LLM-written, so
    none is safe to interpolate into a shell command line. A payload file
    sidesteps shell quoting entirely -- only two agent-controlled paths
    (sweep_dir, payload) ever appear on the command line."""
    parser = argparse.ArgumentParser(description="Persist and render the subsystem synthesis narrative")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subsystem_parser = subparsers.add_parser(
        "update-subsystem", help="Set a subsystem's name + narrative from a JSON payload file"
    )
    subsystem_parser.add_argument("sweep_dir")
    subsystem_parser.add_argument(
        "payload", help='Path to a JSON file: {"subsystem_id": "...", "name": "...", "narrative": "..."}'
    )

    overview_parser = subparsers.add_parser(
        "set-overview", help="Set the sweep's top-level overview from a JSON payload file"
    )
    overview_parser.add_argument("sweep_dir")
    overview_parser.add_argument("payload", help='Path to a JSON file: {"overview": "..."}')

    report_parser = subparsers.add_parser("report", help="Render the full report.md for a sweep")
    report_parser.add_argument("sweep_dir")

    args = parser.parse_args()
    db_path = Path(args.sweep_dir) / "understanding.db"

    if args.command == "update-subsystem":
        payload = json.loads(Path(args.payload).read_text())
        update_subsystem(db_path, payload["subsystem_id"], payload["name"], payload["narrative"])
        print(f"Updated subsystem '{payload['subsystem_id']}'")
    elif args.command == "set-overview":
        payload = json.loads(Path(args.payload).read_text())
        set_sweep_overview(db_path, payload["overview"])
        print("Overview set")
    else:
        report_path = Path(args.sweep_dir) / "report.md"
        report_path.write_text(render_full_report(db_path))
        print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
