"""Runnable check for Slice 2: manifest detection, role classification,
and the Detected Stack / Entrypoints report sections."""
import subprocess
import tempfile
from pathlib import Path

from analyze import analyze_local_repo
from report import render_markdown


def make_fixture_repo(root: Path) -> None:
    """A repo with one file per manifest kind, plus entrypoint/test/docs/
    config/unclassified files, to exercise every role and manifest parser.
    Not a realistic package layout — just enough real files to point at.
    """
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)

    (root / "package.json").write_text(
        '{\n'
        '  "name": "demo-app",\n'
        '  "dependencies": {"express": "^4.18.0"},\n'
        '  "devDependencies": {"jest": "^29.0.0"},\n'
        '  "scripts": {"start": "node index.js", "test": "jest"}\n'
        '}\n'
    )
    (root / "index.js").write_text("console.log('hi')\n")

    (root / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo-pkg"\n'
        'dependencies = ["click"]\n'
        '\n'
        '[project.scripts]\n'
        'demo = "demo:main"\n'
    )
    (root / "main.py").write_text("print('hi')\n")

    (root / "requirements.txt").write_text("flask==2.0.1\n# a comment\nrequests>=2.28\n")

    (root / "setup.py").write_text(
        "from setuptools import setup\n"
        "\n"
        "setup(\n"
        "    name='legacy-pkg',\n"
        "    install_requires=['six'],\n"
        ")\n"
    )

    (root / "test_main.py").write_text("def test_ok():\n    assert True\n")
    (root / "README.md").write_text("# Demo\n")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("# Guide\n")
    (root / "tsconfig.json").write_text("{}\n")
    (root / "notes.txt").write_text("just a note\n")

    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=test", "commit", "-q", "-m", "init"],
        cwd=root, check=True,
    )


def make_empty_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "README.md").write_text("# Empty\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=test", "commit", "-q", "-m", "init"],
        cwd=root, check=True,
    )


def test_analyze_local_repo_classifies_roles_and_extracts_manifests():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture_repo(root)

        index = analyze_local_repo(root)
        roles = {f.path: f.role for f in index.files}

        assert roles["main.py"] == "entrypoint"
        assert roles["index.js"] == "entrypoint"
        assert roles["test_main.py"] == "test"
        assert roles["README.md"] == "docs"
        assert roles["docs/guide.md"] == "docs"
        assert roles["tsconfig.json"] == "config"
        assert roles["package.json"] == "config"
        assert roles["pyproject.toml"] == "config"
        assert roles["requirements.txt"] == "config"
        assert roles["setup.py"] == "config"
        assert roles["notes.txt"] == "unclassified"

        manifests_by_kind = {m.kind: m for m in index.manifests}
        assert set(manifests_by_kind) == {
            "npm", "python-pyproject", "python-requirements", "python-setuptools",
        }

        npm = manifests_by_kind["npm"]
        assert npm.name == "demo-app"
        assert set(npm.dependencies) == {"express", "jest"}
        assert npm.scripts == {"start": "node index.js", "test": "jest"}

        pyproject = manifests_by_kind["python-pyproject"]
        assert pyproject.name == "demo-pkg"
        assert pyproject.dependencies == ["click"]
        assert pyproject.scripts == {"demo": "demo:main"}

        requirements = manifests_by_kind["python-requirements"]
        assert requirements.dependencies == ["flask==2.0.1", "requests>=2.28"]

        setup_py = manifests_by_kind["python-setuptools"]
        assert setup_py.name == "legacy-pkg"
        assert setup_py.dependencies == ["six"]


def test_render_markdown_includes_detected_stack_and_entrypoints():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture_repo(root)
        index = analyze_local_repo(root)

        report = render_markdown(index)

        assert "## Detected Stack" in report
        assert "## Entrypoints" in report
        assert "package.json" in report
        assert "express" in report
        assert "`main.py`" in report
        assert "`index.js`" in report


def test_render_markdown_handles_repo_with_no_manifests():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_empty_repo(root)
        index = analyze_local_repo(root)

        report = render_markdown(index)

        assert "No manifest files detected." in report
        assert "No entrypoints detected." in report


if __name__ == "__main__":
    test_analyze_local_repo_classifies_roles_and_extracts_manifests()
    test_render_markdown_includes_detected_stack_and_entrypoints()
    test_render_markdown_handles_repo_with_no_manifests()
    print("ok")
