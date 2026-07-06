"""Runnable check for Slice 14: persisting and listing verified per-edge
semantic descriptions. The Agent A/Agent B verification itself is
verified by one real manual sweep per SKILL.md, hand-reviewed for
hallucination -- this test only covers the deterministic DB writer and
the edge/description join."""
import sqlite3
import tempfile
from pathlib import Path

from edges import add_edge_description, load_edges_with_descriptions


def _seed_sweep_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sweeps (id INTEGER PRIMARY KEY, repo_path TEXT, repo_name TEXT, commit_sha TEXT, branch TEXT, started_at TEXT);
        CREATE TABLE edges (sweep_id INTEGER, source TEXT, target TEXT, type TEXT, label TEXT);
        CREATE TABLE edge_descriptions (sweep_id INTEGER, source TEXT, target TEXT, description TEXT, evidence_files TEXT, confidence TEXT);
        """
    )
    conn.execute(
        "INSERT INTO sweeps (id, repo_path, repo_name, commit_sha, branch, started_at) "
        "VALUES (1, '/tmp/x', 'x', '', '', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO edges (sweep_id, source, target, type, label) VALUES "
        "(1, 'module:app', 'module:lib', 'imports', 'imports'), "
        "(1, 'module:app', 'manifest:requirements.txt', 'depends_on', 'depends on')"
    )
    conn.commit()
    conn.close()


def test_add_edge_description_persists_a_row():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path)

        add_edge_description(db_path, "module:app", "module:lib", "Calls format_request() from lib.", ["app/main.py"])

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT source, target, description, confidence FROM edge_descriptions").fetchall()
        conn.close()
        assert rows == [("module:app", "module:lib", "Calls format_request() from lib.", "semantic")]


def test_described_edge_shows_description_not_static_label():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path)
        add_edge_description(db_path, "module:app", "module:lib", "Calls format_request() from lib.", ["app/main.py"])

        edges = load_edges_with_descriptions(db_path)

        described = next(e for e in edges if e["target"] == "module:lib")
        assert described["description"] == "Calls format_request() from lib."
        assert described["evidence_files"] == ["app/main.py"]


def test_undescribed_edge_falls_back_to_static_label():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "understanding.db"
        _seed_sweep_db(db_path)

        edges = load_edges_with_descriptions(db_path)

        undescribed = next(e for e in edges if e["target"] == "manifest:requirements.txt")
        assert "description" not in undescribed
        assert undescribed["label"] == "depends on"


if __name__ == "__main__":
    test_add_edge_description_persists_a_row()
    test_described_edge_shows_description_not_static_label()
    test_undescribed_edge_falls_back_to_static_label()
    print("ok")
