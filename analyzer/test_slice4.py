"""Runnable check for Slice 4: per-module "start here" grouping, suggested
read order, and the Start Here report section."""
import subprocess
import tempfile
from pathlib import Path

from analyze import analyze_local_repo
from report import render_markdown


def _git_init_and_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=test", "commit", "-q", "-m", "init"],
        cwd=root, check=True,
    )


def make_modules_fixture_repo(root: Path) -> None:
    """A repo with 4 distinct modules: one with an entrypoint (`app/`), the
    repo root (a manifest, no entrypoint), a recognized-name module with
    neither (`tests/`), and an unrecognized-name module with neither
    (`widgets/`)."""
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text("print('hi')\n")

    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n")

    (root / "widgets").mkdir()
    (root / "widgets" / "helpers.py").write_text("def helper():\n    pass\n")

    (root / "requirements.txt").write_text("flask==2.0.1\n")
    (root / "README.md").write_text("# Fixture\n")

    _git_init_and_commit(root)


def make_flat_fixture_repo(root: Path) -> None:
    """A repo with no subdirectories at all — everything is at the repo
    root, forming a single module (edge case: very small/flat repos)."""
    (root / "index.js").write_text("console.log('hi')\n")
    (root / "README.md").write_text("# Flat\n")
    _git_init_and_commit(root)


def test_modules_are_ordered_entrypoint_then_manifest_then_rest():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_modules_fixture_repo(root)

        index = analyze_local_repo(root)
        names = [m.name for m in index.modules]

        assert names == ["app", "(repo root)", "tests", "widgets"]


def test_key_files_and_facts_are_traceable_to_real_paths():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_modules_fixture_repo(root)

        index = analyze_local_repo(root)
        real_paths = {f.path for f in index.files}
        app_module = next(m for m in index.modules if m.name == "app")
        root_module = next(m for m in index.modules if m.name == "(repo root)")

        assert app_module.key_files == ["app/main.py"]
        assert set(app_module.key_files).issubset(real_paths)
        assert app_module.has_entrypoint is True
        assert "app/main.py" in app_module.description

        assert root_module.key_files[0] == "requirements.txt"
        assert root_module.has_manifest is True


def test_description_distinguishes_fact_from_inference():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_modules_fixture_repo(root)

        index = analyze_local_repo(root)
        tests_module = next(m for m in index.modules if m.name == "tests")
        widgets_module = next(m for m in index.modules if m.name == "widgets")

        assert "1 Python file" in tests_module.description
        assert "test suite" in tests_module.description
        assert "inferred from naming, not verified" in tests_module.description

        assert "isn't inferred here" in widgets_module.description


def test_flat_repo_with_no_subdirectories_yields_one_root_module():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_flat_fixture_repo(root)

        index = analyze_local_repo(root)

        assert [m.name for m in index.modules] == ["(repo root)"]
        assert index.modules[0].file_count == 2

        report = render_markdown(index)
        assert "## Start Here" in report
        assert "### (repo root)" in report


def test_render_markdown_lists_modules_in_read_order():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_modules_fixture_repo(root)
        index = analyze_local_repo(root)

        report = render_markdown(index)

        assert "## Start Here" in report
        app_pos = report.index("### app")
        root_pos = report.index("### (repo root)")
        tests_pos = report.index("### tests")
        widgets_pos = report.index("### widgets")
        assert app_pos < root_pos < tests_pos < widgets_pos
        assert "Key files: `app/main.py`" in report


def test_render_markdown_shows_no_modules_fallback_when_empty():
    index = analyze_local_repo(Path(tempfile.mkdtemp()))  # empty dir, no git, no files
    report = render_markdown(index)

    assert "## Start Here" in report
    assert "No modules detected." in report


if __name__ == "__main__":
    test_modules_are_ordered_entrypoint_then_manifest_then_rest()
    test_key_files_and_facts_are_traceable_to_real_paths()
    test_description_distinguishes_fact_from_inference()
    test_flat_repo_with_no_subdirectories_yields_one_root_module()
    test_render_markdown_lists_modules_in_read_order()
    test_render_markdown_shows_no_modules_fallback_when_empty()
    print("ok")
