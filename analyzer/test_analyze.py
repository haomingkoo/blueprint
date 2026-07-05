"""Runnable check for Issue 1: repo -> structured JSON facts."""
import subprocess
import tempfile
from pathlib import Path

from analyze import analyze_local_repo


def make_fixture_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "main.py").write_text("print('hi')\n")
    (root / "app.js").write_text("console.log('hi')\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "ignored.js").write_text("// should be ignored\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=test", "commit", "-q", "-m", "init"],
        cwd=root, check=True,
    )


def test_analyze_local_repo_scans_files_and_ignores_generated_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture_repo(root)

        index = analyze_local_repo(root)

        paths = {f.path for f in index.files}
        assert paths == {"main.py", "app.js"}
        assert index.language_counts == {"Python": 1, "JavaScript": 1}
        assert index.repo.commit_sha != ""
        assert index.repo.branch != ""


if __name__ == "__main__":
    test_analyze_local_repo_scans_files_and_ignores_generated_dirs()
    print("ok")
