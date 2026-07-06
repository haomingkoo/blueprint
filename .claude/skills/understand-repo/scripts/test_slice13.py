"""Runnable check for Slice 13: the multi-page HTML site. Covers the
deterministic renderer only (fixture data) -- and specifically the slug-
collision fix, since two subsystems whose names differ only by case used
to silently overwrite each other's page (and a subsystem named "index"
could clobber the site's own homepage)."""
import sqlite3
import tempfile
from pathlib import Path

from site_builder import _assign_unique_slugs, build_site, load_sweep_data


def _seed_sweep_db(db_path: Path, subsystem_names: list[tuple[str, str]]) -> None:
    """`subsystem_names` is a list of (id, name) pairs, one module per
    subsystem, named after the subsystem id for simplicity."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sweeps (id INTEGER PRIMARY KEY, repo_path TEXT, repo_name TEXT, commit_sha TEXT, branch TEXT, started_at TEXT, overview TEXT);
        CREATE TABLE subsystems (id TEXT PRIMARY KEY, sweep_id INTEGER, name TEXT, narrative TEXT);
        CREATE TABLE module_subsystem (sweep_id INTEGER, module_name TEXT, subsystem_id TEXT);
        CREATE TABLE modules (sweep_id INTEGER, module_name TEXT, key_files TEXT);
        CREATE TABLE semantic_summaries (sweep_id INTEGER, module_name TEXT, summary_text TEXT, evidence_files TEXT, verified INTEGER, confidence TEXT);
        CREATE TABLE edges (sweep_id INTEGER, source TEXT, target TEXT, type TEXT, label TEXT, evidence TEXT);
        CREATE TABLE edge_descriptions (sweep_id INTEGER, source TEXT, target TEXT, description TEXT, evidence_files TEXT, confidence TEXT);
        CREATE TABLE module_files (sweep_id INTEGER, module_name TEXT, path TEXT, role TEXT, language TEXT);
        """
    )
    conn.execute(
        "INSERT INTO sweeps (id, repo_path, repo_name, commit_sha, branch, started_at, overview) "
        "VALUES (1, '/tmp/x', 'demo-repo', 'abc1234', 'main', '2026-01-01', 'A demo repo.')"
    )
    for sid, name in subsystem_names:
        module_name = sid
        conn.execute("INSERT INTO subsystems (id, sweep_id, name) VALUES (?, 1, ?)", (sid, name))
        conn.execute(
            "INSERT INTO module_subsystem (sweep_id, module_name, subsystem_id) VALUES (1, ?, ?)",
            (module_name, sid),
        )
        conn.execute(
            "INSERT INTO modules (sweep_id, module_name, key_files) VALUES (1, ?, '[]')", (module_name,)
        )
        conn.execute(
            "INSERT INTO module_files (sweep_id, module_name, path, role, language) VALUES (1, ?, ?, 'source', 'Python')",
            (module_name, f"{module_name}/x.py"),
        )
    conn.commit()
    conn.close()


def test_assign_unique_slugs_dedupes_case_insensitive_collisions():
    subsystems = [{"name": "Core"}, {"name": "core"}]

    _assign_unique_slugs(subsystems)

    slugs = [s["slug"] for s in subsystems]
    assert len(set(slugs)) == 2
    assert slugs[0] != slugs[1]


def test_assign_unique_slugs_never_produces_index():
    subsystems = [{"name": "Index"}, {"name": "index"}]

    _assign_unique_slugs(subsystems)

    assert "index" not in [s["slug"] for s in subsystems]


def test_build_site_writes_a_page_per_subsystem_even_with_colliding_names(tmp_path):
    sweep_dir = tmp_path / "sweep"
    sweep_dir.mkdir()
    _seed_sweep_db(sweep_dir / "understanding.db", [("subsystem-1", "Core"), ("subsystem-2", "core")])

    site_dir = build_site(sweep_dir)

    html_files = sorted(p.name for p in site_dir.glob("*.html"))
    assert "index.html" in html_files
    assert len(html_files) == 3  # index + 2 distinct subsystem pages, no overwrite


def test_build_site_shows_verified_summary_and_edge_description(tmp_path):
    sweep_dir = tmp_path / "sweep"
    sweep_dir.mkdir()
    db_path = sweep_dir / "understanding.db"
    _seed_sweep_db(db_path, [("subsystem-1", "app")])
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO semantic_summaries (sweep_id, module_name, summary_text, evidence_files, verified, confidence) "
        "VALUES (1, 'subsystem-1', 'Handles HTTP routing.', '[\"subsystem-1/x.py\"]', 1, 'semantic')"
    )
    conn.execute(
        "INSERT INTO edges (sweep_id, source, target, type, label, evidence) VALUES "
        "(1, 'module:subsystem-1', 'manifest:requirements.txt', 'depends_on', 'depends on', '[]')"
    )
    conn.execute(
        "INSERT INTO edge_descriptions (sweep_id, source, target, description, evidence_files, confidence) VALUES "
        "(1, 'module:subsystem-1', 'manifest:requirements.txt', 'Pins FastAPI as a runtime dependency.', '[]', 'semantic')"
    )
    conn.commit()
    conn.close()

    site_dir = build_site(sweep_dir)

    data = load_sweep_data(db_path)
    subsystem_page = (site_dir / f"{data['subsystems'][0]['slug']}.html").read_text()
    assert "Handles HTTP routing." in subsystem_page
    assert "Pins FastAPI as a runtime dependency." in subsystem_page


if __name__ == "__main__":
    test_assign_unique_slugs_dedupes_case_insensitive_collisions()
    test_assign_unique_slugs_never_produces_index()
    test_build_site_writes_a_page_per_subsystem_even_with_colliding_names()
    test_build_site_shows_verified_summary_and_edge_description()
    print("ok")
