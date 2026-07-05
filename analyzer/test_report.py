"""Runnable check for Slice 1: RepoIndex -> Markdown report."""
from analyze import FileInfo, RepoIndex, RepoInfo
from report import render_markdown


def test_render_markdown_includes_repo_metadata_and_language_breakdown():
    index = RepoIndex(
        repo=RepoInfo(
            provider="github", owner="psf", name="requests",
            branch="main", commit_sha="abc1234567", url="https://github.com/psf/requests",
        ),
        files=[
            FileInfo(path="requests/api.py", language="Python", size=100),
            FileInfo(path="requests/models.py", language="Python", size=200),
            FileInfo(path="setup.js", language="JavaScript", size=50),
        ],
        language_counts={"Python": 2, "JavaScript": 1},
    )

    report = render_markdown(index)

    assert "psf/requests" in report
    assert "abc1234" in report
    assert "3 files across 2 languages" in report
    assert "dominated by Python" in report
    assert "Python: 2 files" in report
    assert "JavaScript: 1 file" in report


if __name__ == "__main__":
    test_render_markdown_includes_repo_metadata_and_language_breakdown()
    print("ok")
