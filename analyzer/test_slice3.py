"""Runnable check for Slice 3: review findings (missing tests, secrets risk,
dependency risk) and the Review Findings report section."""
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


def make_findings_fixture_repo(root: Path) -> None:
    """A repo that should trigger exactly one finding per Slice 3 category."""
    (root / "main.py").write_text("print('hi')\n")  # entrypoint, no test anywhere

    (root / ".env").write_text("SOME_VAR=1\n")  # secrets-risk: no .env.example sibling

    (root / "requirements.txt").write_text("flask\nrequests\n")  # dependency-risk: zero pins

    _git_init_and_commit(root)


def make_clean_fixture_repo(root: Path) -> None:
    """A repo that should trigger no findings: covered entrypoint, no .env,
    pinned dependencies, small dependency list."""
    (root / "main.py").write_text("print('hi')\n")
    (root / "test_main.py").write_text("def test_ok():\n    assert True\n")

    (root / "requirements.txt").write_text("flask==2.0.1\nrequests>=2.28\n")

    _git_init_and_commit(root)


def test_generates_missing_test_coverage_finding_for_uncovered_entrypoint():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_findings_fixture_repo(root)

        index = analyze_local_repo(root)
        findings = [f for f in index.findings if f.category == "missing-tests"]

        assert len(findings) == 1
        assert findings[0].evidence == ["main.py"]
        assert findings[0].confidence == "heuristic"


def test_generates_secrets_risk_finding_for_env_without_example():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_findings_fixture_repo(root)

        index = analyze_local_repo(root)
        findings = [f for f in index.findings if f.category == "secrets-risk"]

        assert len(findings) == 1
        assert findings[0].evidence == [".env"]
        assert findings[0].severity == "high"


def test_generates_dependency_risk_finding_for_unpinned_requirements():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_findings_fixture_repo(root)

        index = analyze_local_repo(root)
        findings = [f for f in index.findings if f.category == "dependency-risk"]

        assert len(findings) == 1
        assert findings[0].evidence == ["requirements.txt"]
        assert "pins no dependency versions" in findings[0].title


def test_generates_dependency_risk_finding_for_large_dependency_list():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        deps = "\n".join(f"pkg{i}=={i}.0.0" for i in range(35))
        (root / "requirements.txt").write_text(deps + "\n")
        _git_init_and_commit(root)

        index = analyze_local_repo(root)
        findings = [f for f in index.findings if f.category == "dependency-risk"]

        assert len(findings) == 1
        assert "35 dependencies" in findings[0].title


def test_clean_repo_has_no_findings():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_clean_fixture_repo(root)

        index = analyze_local_repo(root)

        assert index.findings == []


def test_render_markdown_lists_findings_by_category():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_findings_fixture_repo(root)
        index = analyze_local_repo(root)

        report = render_markdown(index)

        assert "## Review Findings" in report
        assert "### Missing Test Coverage" in report
        assert "### Config & Secrets Risk" in report
        assert "### Dependency Risk" in report
        assert "`main.py`" in report
        assert "`.env`" in report
        assert "`requirements.txt`" in report
        assert "No findings in this category." not in report


def test_render_markdown_shows_no_findings_fallback_per_category():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_clean_fixture_repo(root)
        index = analyze_local_repo(root)

        report = render_markdown(index)

        assert "## Review Findings" in report
        assert report.count("No findings in this category.") == 3


if __name__ == "__main__":
    test_generates_missing_test_coverage_finding_for_uncovered_entrypoint()
    test_generates_secrets_risk_finding_for_env_without_example()
    test_generates_dependency_risk_finding_for_unpinned_requirements()
    test_generates_dependency_risk_finding_for_large_dependency_list()
    test_clean_repo_has_no_findings()
    test_render_markdown_lists_findings_by_category()
    test_render_markdown_shows_no_findings_fallback_per_category()
    print("ok")
