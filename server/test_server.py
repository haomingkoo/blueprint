"""Runnable check for Slice 5: FastAPI wrapper around the analyzer pipeline.

Uses `fastapi.testclient.TestClient` (httpx-backed) rather than plain
asserts against raw functions, since driving the actual HTTP layer is the
point of this check. `analyze_github_repo` is stubbed out at the module
level (no network/git calls), matching testing.md's "mock external
dependencies" rule.
"""
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

import main  # noqa: E402 (sys.path setup must run first)
from analyze import FileInfo, Flow, Node, RepoIndex, RepoInfo  # noqa: E402 (analyzer dir added to sys.path by importing main)

client = TestClient(main.app)


def _fixture_index() -> RepoIndex:
    return RepoIndex(
        repo=RepoInfo(
            provider="github", owner="octocat", name="Hello-World",
            branch="master", commit_sha="abc1234567890",
            url="https://github.com/octocat/Hello-World",
        ),
        files=[FileInfo(path="README", language="Other", size=10, role="docs")],
        language_counts={"Other": 1},
    )


def _fixture_index_with_graph_and_flow() -> RepoIndex:
    """A Slice 8-flavored fixture with real nodes/edges/flows, for exercising
    the Mermaid export's flow_index branch."""
    index = _fixture_index()
    node = Node(id="module:(repo root)", label="(repo root)", type="module",
                file_paths=["README"], evidence=["README"], confidence="structural")
    index.nodes = [node]
    index.edges = []
    index.flows = [Flow(
        title="Entrypoint reachability: (repo root)", nodes=[node], edges=[],
        explanation="no outgoing imports detected", evidence=["README"], confidence="heuristic",
    )]
    return index


def test_analyze_returns_repo_index_json_for_a_valid_url():
    with patch.object(main, "analyze_github_repo", return_value=_fixture_index()):
        response = client.post(
            "/api/analyze", json={"repo_url": "https://github.com/octocat/Hello-World"}
        )

    assert response.status_code == 200

    body = response.json()

    assert body["repo"]["owner"] == "octocat"
    assert body["repo"]["name"] == "Hello-World"
    assert body["language_counts"] == {"Other": 1}


def test_analyze_rejects_non_github_url_with_clean_400():
    response = client.post("/api/analyze", json={"repo_url": "not-a-url"})

    assert response.status_code == 400
    assert "github" in response.json()["error"].lower()


def test_analyze_rejects_blank_url_with_clean_400():
    response = client.post("/api/analyze", json={"repo_url": "   "})

    assert response.status_code == 400
    assert "required" in response.json()["error"].lower()


def test_analyze_translates_clone_failure_into_clean_400_not_a_traceback():
    def _raise_clone_error(url: str) -> RepoIndex:
        raise subprocess.CalledProcessError(
            returncode=128, cmd=["git", "clone"], stderr=b"fatal: repository not found"
        )

    with patch.object(main, "analyze_github_repo", side_effect=_raise_clone_error):
        response = client.post(
            "/api/analyze", json={"repo_url": "https://github.com/owner/does-not-exist"}
        )

    assert response.status_code == 400

    body = response.json()

    assert "error" in body
    assert "Traceback" not in body["error"]
    assert "fatal:" not in body["error"]  # raw git stderr must not leak to the client


def test_analyze_missing_field_returns_422_not_a_crash():
    response = client.post("/api/analyze", json={})

    assert response.status_code == 422


def test_static_index_page_is_served_at_root():
    response = client.get("/")

    assert response.status_code == 200
    assert "Blueprint" in response.text
    assert "analyze-form" in response.text


# ---------- Slice 8: export endpoints ----------
# Each posts the same `asdict(index)` JSON shape `/api/analyze` returns —
# no re-clone, no re-analyze, just reconstruction + rendering.


def test_export_markdown_reuses_render_markdown_as_is():
    response = client.post("/api/export/markdown", json={"index": asdict(_fixture_index())})

    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "octocat/Hello-World" in response.text
    assert "abc1234" in response.text  # commit SHA present


def test_export_mermaid_defaults_to_the_full_graph():
    index = _fixture_index_with_graph_and_flow()

    response = client.post("/api/export/mermaid", json={"index": asdict(index)})

    assert response.status_code == 200
    assert "graph LR" in response.text
    assert "%% Repo: https://github.com/octocat/Hello-World" in response.text
    assert "(repo root)" in response.text


def test_export_mermaid_with_flow_index_scopes_to_that_flow():
    index = _fixture_index_with_graph_and_flow()

    response = client.post(
        "/api/export/mermaid", json={"index": asdict(index), "flow_index": 0}
    )

    assert response.status_code == 200
    assert "%% Entrypoint reachability: (repo root)" in response.text


def test_export_mermaid_rejects_an_out_of_range_flow_index():
    index = _fixture_index_with_graph_and_flow()

    response = client.post(
        "/api/export/mermaid", json={"index": asdict(index), "flow_index": 5}
    )

    assert response.status_code == 400


def test_export_html_returns_a_standalone_document_with_download_headers():
    response = client.post("/api/export/html", json={"index": asdict(_fixture_index())})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.startswith("<!doctype html>")
    assert "https://github.com/octocat/Hello-World" in response.text
    assert "<link" not in response.text.lower()
    assert "<script" not in response.text.lower()


def test_export_endpoints_reject_malformed_index_with_clean_400():
    response = client.post("/api/export/markdown", json={"index": {"not": "a repo index"}})

    assert response.status_code == 400
    assert "error" in response.json()


if __name__ == "__main__":
    test_analyze_returns_repo_index_json_for_a_valid_url()
    test_analyze_rejects_non_github_url_with_clean_400()
    test_analyze_rejects_blank_url_with_clean_400()
    test_analyze_translates_clone_failure_into_clean_400_not_a_traceback()
    test_analyze_missing_field_returns_422_not_a_crash()
    test_static_index_page_is_served_at_root()
    test_export_markdown_reuses_render_markdown_as_is()
    test_export_mermaid_defaults_to_the_full_graph()
    test_export_mermaid_with_flow_index_scopes_to_that_flow()
    test_export_mermaid_rejects_an_out_of_range_flow_index()
    test_export_html_returns_a_standalone_document_with_download_headers()
    test_export_endpoints_reject_malformed_index_with_clean_400()
    print("ok")
