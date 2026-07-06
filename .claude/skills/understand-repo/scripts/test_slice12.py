"""Runnable check for Slice 12: persisting and rendering the subsystem
synthesis narrative. The synthesis agent itself is verified by one real
manual sweep per SKILL.md, hand-reviewed to confirm it introduces no new
structural claims -- this test only covers the deterministic DB writer and
the full report.md renderer."""
import sqlite3
import tempfile
from pathlib import Path

from synthesis import render_full_report, set_sweep_overview, update_subsystem


def _seed_sweep_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sweeps (id INTEGER PRIMARY KEY, repo_path TEXT, repo_name TEXT, commit_sha TEXT, branch TEXT, started_at TEXT, overview TEXT);
        CREATE TABLE subsystems (id TEXT PRIMARY KEY, sweep_id INTEGER, name TEXT, narrative TEXT);
        CREATE TABLE module_subsystem (sweep_id INTEGER, module_name TEXT, subsystem_id TEXT);
        CREATE TABLE semantic_summaries (sweep_id INTEGER, module_name TEXT, summary_text TEXT, evidence_files TEXT, verified INTEGER, confidence TEXT);
        CREATE TABLE edges (sweep_id INTEGER, source TEXT, target TEXT, type TEXT, label TEXT, evidence TEXT);
        CREATE TABLE edge_descriptions (sweep_id INTEGER, source TEXT, target TEXT, description TEXT, evidence_files TEXT, confidence TEXT);
        """
    )
    conn.execute(
        "INSERT INTO sweeps (id, repo_path, repo_name, commit_sha, branch, started_at) "
        "VALUES (1, '/tmp/x', 'demo-repo', '', '', '2026-01-01')"
    )
    conn.execute("INSERT INTO subsystems (id, sweep_id, name) VALUES ('subsystem-1', 1, 'app')")
    conn.execute("INSERT INTO subsystems (id, sweep_id, name) VALUES ('subsystem-2', 1, 'lib')")
    conn.execute(
        "INSERT INTO module_subsystem (sweep_id, module_name, subsystem_id) VALUES (1, 'app', 'subsystem-1')"
    )
    conn.execute(
        "INSERT INTO module_subsystem (sweep_id, module_name, subsystem_id) VALUES (1, 'lib', 'subsystem-2')"
    )
    conn.commit()
    conn.close()


def test_update_subsystem_persists_name_and_narrative():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path)

        update_subsystem(db_path, "subsystem-1", "Web Layer", "Handles incoming HTTP requests.")

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT name, narrative FROM subsystems WHERE id = 'subsystem-1'").fetchone()
        conn.close()
        assert row == ("Web Layer", "Handles incoming HTTP requests.")


def test_report_includes_overview_and_subsystem_sections():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path)
        set_sweep_overview(db_path, "This repo has two subsystems: a web layer and a shared library.")
        update_subsystem(db_path, "subsystem-1", "Web Layer", "Handles incoming HTTP requests.")

        report = render_full_report(db_path)

        assert "# demo-repo — Understanding Report" in report
        assert "This repo has two subsystems" in report
        assert "### Web Layer" in report
        assert "Handles incoming HTTP requests." in report
        assert "**Modules:** app" in report
        assert "# Edge Descriptions — verified" in report


def test_report_marks_unsynthesized_subsystem_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path)

        report = render_full_report(db_path)

        assert "_No synthesis overview yet" in report
        assert "### lib" in report
        assert "_No synthesized narrative yet for this subsystem._" in report


if __name__ == "__main__":
    test_update_subsystem_persists_name_and_narrative()
    test_report_includes_overview_and_subsystem_sections()
    test_report_marks_unsynthesized_subsystem_explicitly()
    print("ok")
