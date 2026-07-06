#!/usr/bin/env python3
"""understand-repo Slice 10: cluster a local repo's modules into subsystems
and persist the result. No LLM yet -- see docs/prd-understand-repo.md for
the full plan (Slices 11-13 add the semantic layer on top of this).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# scripts/sweep.py -> understand-repo/ -> skills/ -> .claude/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parents[4]
ANALYZER_DIR = REPO_ROOT / "analyzer"
if str(ANALYZER_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYZER_DIR))

from analyze import (  # noqa: E402
    Edge, FileInfo, Module, Subsystem, analyze_local_repo, cluster_modules, module_name_for_path,
)

UNDERSTANDING_ROOT = REPO_ROOT / ".understanding"


def run_sweep(repo_path: Path) -> Path:
    index = analyze_local_repo(repo_path)
    subsystems = cluster_modules(index.nodes, index.edges)

    repo_name = index.repo.name or repo_path.name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    sha_suffix = f"-{index.repo.commit_sha[:7]}" if index.repo.commit_sha else ""
    sweep_dir = UNDERSTANDING_ROOT / repo_name / f"{timestamp}{sha_suffix}"
    sweep_dir.mkdir(parents=True)

    _write_sweep(
        sweep_dir / "understanding.db", repo_path, repo_name,
        index.repo.commit_sha, index.repo.branch, subsystems,
        index.modules, index.edges, index.files,
    )
    _update_latest_pointer(sweep_dir)
    _print_subsystems(subsystems)
    _print_module_key_files(index.modules)
    return sweep_dir


def _write_sweep(
    db_path: Path, repo_path: Path, repo_name: str,
    commit_sha: str, branch: str, subsystems: list[Subsystem],
    modules: list[Module], edges: list[Edge], files: list[FileInfo],
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sweeps (
                id INTEGER PRIMARY KEY,
                repo_path TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                commit_sha TEXT,
                branch TEXT,
                started_at TEXT NOT NULL,
                overview TEXT
            );
            CREATE TABLE subsystems (
                id TEXT PRIMARY KEY,
                sweep_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                narrative TEXT
            );
            CREATE TABLE module_subsystem (
                sweep_id INTEGER NOT NULL,
                module_name TEXT NOT NULL,
                subsystem_id TEXT NOT NULL
            );
            CREATE TABLE semantic_summaries (
                sweep_id INTEGER NOT NULL,
                module_name TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                evidence_files TEXT NOT NULL,
                verified INTEGER NOT NULL,
                confidence TEXT NOT NULL,
                UNIQUE (sweep_id, module_name)
            );
            CREATE TABLE modules (
                sweep_id INTEGER NOT NULL,
                module_name TEXT NOT NULL,
                key_files TEXT NOT NULL
            );
            CREATE TABLE edges (
                sweep_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                type TEXT NOT NULL,
                label TEXT NOT NULL,
                evidence TEXT NOT NULL
            );
            CREATE TABLE edge_descriptions (
                sweep_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                description TEXT NOT NULL,
                evidence_files TEXT NOT NULL,
                confidence TEXT NOT NULL,
                UNIQUE (sweep_id, source, target)
            );
            CREATE TABLE module_files (
                sweep_id INTEGER NOT NULL,
                module_name TEXT NOT NULL,
                path TEXT NOT NULL,
                role TEXT NOT NULL,
                language TEXT NOT NULL
            );
            """
        )
        started_at = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO sweeps (repo_path, repo_name, commit_sha, branch, started_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(repo_path), repo_name, commit_sha, branch, started_at),
        )
        sweep_id = cursor.lastrowid
        for s in subsystems:
            conn.execute(
                "INSERT INTO subsystems (id, sweep_id, name) VALUES (?, ?, ?)",
                (s.id, sweep_id, s.name),
            )
            conn.executemany(
                "INSERT INTO module_subsystem (sweep_id, module_name, subsystem_id) VALUES (?, ?, ?)",
                [(sweep_id, module_name, s.id) for module_name in s.module_names],
            )
        conn.executemany(
            "INSERT INTO modules (sweep_id, module_name, key_files) VALUES (?, ?, ?)",
            [(sweep_id, m.name, json.dumps(m.key_files)) for m in modules],
        )
        conn.executemany(
            "INSERT INTO edges (sweep_id, source, target, type, label, evidence) VALUES (?, ?, ?, ?, ?, ?)",
            [(sweep_id, e.source, e.target, e.type, e.label, json.dumps(e.evidence)) for e in edges],
        )
        conn.executemany(
            "INSERT INTO module_files (sweep_id, module_name, path, role, language) VALUES (?, ?, ?, ?, ?)",
            [(sweep_id, module_name_for_path(f.path), f.path, f.role, f.language) for f in files],
        )
        conn.commit()
    finally:
        conn.close()


def _update_latest_pointer(sweep_dir: Path) -> None:
    """Atomic: build the new symlink under a throwaway name, then
    `os.replace` it over `latest` in one step. The previous check-then-
    unlink-then-create approach was three separate syscalls -- two
    sweeps of the same repo running close together could crash on an
    unlink()/symlink_to() race; a single rename can't leave a half-
    finished pointer."""
    latest_link = sweep_dir.parent / "latest"
    tmp_link = sweep_dir.parent / f".latest-{os.getpid()}.tmp"
    tmp_link.symlink_to(sweep_dir.name)
    os.replace(tmp_link, latest_link)


def _print_subsystems(subsystems: list[Subsystem]) -> None:
    """Prints each subsystem's real `id` alongside its name -- Phase 3's
    `synthesis.py update-subsystem` requires that exact id, and it cannot
    be reliably guessed from print order (see docs/HANDOFF.md)."""
    count = len(subsystems)
    print(f"{count} subsystem{'s' if count != 1 else ''} detected:\n")
    for s in subsystems:
        n = len(s.module_names)
        print(f"- [{s.id}] {s.name} ({n} module{'s' if n != 1 else ''}): {', '.join(s.module_names)}")


def _print_module_key_files(modules: list[Module]) -> None:
    """Printed so the Slice 11 semantic phase (see SKILL.md) knows which
    real files to hand each module's Agent A / Agent B pair -- reuses the
    same key_files the structural pass already computed, no new scanning."""
    print("\nModule key files (evidence for the semantic phase):\n")
    for m in modules:
        print(f"- {m.name}: {', '.join(m.key_files) if m.key_files else '(no files)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep a local repo and cluster its modules into subsystems")
    parser.add_argument("repo_path", help="Path to a local repo to analyze")
    args = parser.parse_args()
    sweep_dir = run_sweep(Path(args.repo_path).resolve())
    print(f"\nSweep written to {sweep_dir}")


if __name__ == "__main__":
    main()
