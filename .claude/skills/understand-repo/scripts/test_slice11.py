"""Runnable check for Slice 11: persisting and rendering verified
per-module semantic summaries. The LLM stages themselves (Agent A writes,
Agent B refutes) are verified by one real manual sweep per SKILL.md, hand-
reviewed for hallucination -- this test only covers the deterministic DB
writer and Markdown renderer."""
import sqlite3
import tempfile
from pathlib import Path

from semantic import add_semantic_summary, render_semantic_report


def _seed_sweep_db(db_path: Path, module_names: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sweeps (id INTEGER PRIMARY KEY, repo_path TEXT, repo_name TEXT, commit_sha TEXT, branch TEXT, started_at TEXT);
        CREATE TABLE subsystems (id TEXT PRIMARY KEY, sweep_id INTEGER, name TEXT);
        CREATE TABLE module_subsystem (sweep_id INTEGER, module_name TEXT, subsystem_id TEXT);
        CREATE TABLE semantic_summaries (sweep_id INTEGER, module_name TEXT, summary_text TEXT, evidence_files TEXT, verified INTEGER, confidence TEXT);
        """
    )
    conn.execute(
        "INSERT INTO sweeps (id, repo_path, repo_name, commit_sha, branch, started_at) "
        "VALUES (1, '/tmp/x', 'x', '', '', '2026-01-01')"
    )
    for name in module_names:
        conn.execute(
            "INSERT INTO module_subsystem (sweep_id, module_name, subsystem_id) VALUES (1, ?, 'subsystem-1')",
            (name,),
        )
    conn.commit()
    conn.close()


def test_add_semantic_summary_persists_a_row():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path, ["app"])

        add_semantic_summary(db_path, "app", "Handles HTTP routing.", ["app/main.py"])

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT module_name, summary_text, confidence FROM semantic_summaries").fetchall()
        conn.close()
        assert rows == [("app", "Handles HTTP routing.", "semantic")]


def test_report_shows_verified_summary_with_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path, ["app"])
        add_semantic_summary(db_path, "app", "Handles HTTP routing.", ["app/main.py"])

        report = render_semantic_report(db_path)

        assert "## app" in report
        assert "Handles HTTP routing." in report
        assert "app/main.py" in report


def test_report_marks_unverified_module_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path, ["mystery"])

        report = render_semantic_report(db_path)

        assert "## mystery" in report
        assert "No verified semantic summary this sweep" in report


def test_report_covers_every_module_even_with_no_summaries_at_all():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path, ["a", "b"])

        report = render_semantic_report(db_path)

        assert "## a" in report
        assert "## b" in report


if __name__ == "__main__":
    test_add_semantic_summary_persists_a_row()
    test_report_shows_verified_summary_with_evidence()
    test_report_marks_unverified_module_explicitly()
    test_report_covers_every_module_even_with_no_summaries_at_all()
    print("ok")
