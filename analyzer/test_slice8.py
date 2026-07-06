"""Runnable check for Slice 8: Mermaid export (`mermaid.py`) and the
self-contained HTML export (`html_export.py`). Both are pure serializers
over an already-built `RepoIndex` -- no cloning/git needed, so these tests
build a small fixture directly, per the "fixture graph -> expected shape"
style used for Slice 6/7's graph/flow checks."""
from analyze import (
    Edge, FileInfo, Finding, Flow, Manifest, Module, Node, RepoIndex, RepoInfo,
)
from html_export import render_html_report
from mermaid import render_mermaid_flow, render_mermaid_graph


def _fixture_repo_info() -> RepoInfo:
    return RepoInfo(
        provider="github", owner="octocat", name="Hello-World",
        branch="main", commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        url="https://github.com/octocat/Hello-World",
    )


def _fixture_nodes_and_edges() -> tuple[list[Node], list[Edge]]:
    nodes = [
        Node(id="module:app", label="app", type="module",
             file_paths=["app/main.py"], evidence=["app/main.py"], confidence="structural"),
        Node(id="manifest:requirements.txt", label="requirements.txt", type="dependency",
             file_paths=["requirements.txt"], evidence=["requirements.txt"], confidence="structural"),
    ]
    edges = [
        Edge(source="module:app", target="manifest:requirements.txt", type="depends_on",
             label="depends on", evidence=["app/main.py"], confidence="heuristic"),
    ]
    return nodes, edges


def _fixture_index() -> RepoIndex:
    nodes, edges = _fixture_nodes_and_edges()
    flow = Flow(
        title="Entrypoint reachability: app",
        nodes=nodes, edges=edges,
        explanation="Starting from the entrypoint in `app/`, this traces 1 detected edge.",
        evidence=["app/main.py", "requirements.txt"],
        confidence="heuristic",
    )
    return RepoIndex(
        repo=_fixture_repo_info(),
        files=[
            FileInfo(path="app/main.py", language="Python", size=10, role="entrypoint"),
            FileInfo(path="requirements.txt", language="Other", size=5, role="config"),
        ],
        language_counts={"Python": 1, "Other": 1},
        manifests=[Manifest(
            path="requirements.txt", kind="python-requirements", name="",
            dependencies=["flask==2.0.1"], scripts={},
        )],
        findings=[Finding(
            severity="medium", category="missing-tests",
            title="No test coverage found near entrypoint `app/main.py`",
            evidence=["app/main.py"], explanation="No nearby test found.",
            recommendation="Add a test.", confidence="heuristic",
        )],
        modules=[Module(
            name="app", file_count=1, key_files=["app/main.py"],
            has_entrypoint=True, has_manifest=False,
            description="1 file. Inferred: main application code.",
        )],
        nodes=nodes, edges=edges, flows=[flow],
    )


# ---------- Mermaid ----------

def test_render_mermaid_graph_includes_repo_url_and_commit_as_comments():
    mermaid = render_mermaid_graph(_fixture_index())

    assert "%% Repo: https://github.com/octocat/Hello-World" in mermaid
    assert "%% Commit: abcdef1" in mermaid  # short SHA, same convention as report.py
    assert mermaid.count("graph LR") == 1


def test_render_mermaid_graph_renders_every_node_and_edge():
    mermaid = render_mermaid_graph(_fixture_index())

    assert "module: app" in mermaid
    assert "dependency: requirements.txt" in mermaid
    assert "-.->" in mermaid  # depends_on edges are rendered dashed
    assert "depends on" in mermaid


def test_render_mermaid_flow_scopes_to_the_selected_flow_only():
    index = _fixture_index()
    # A node in the full graph that the flow (a real, smaller subset)
    # should not include.
    extra_node = Node(id="module:other", label="other", type="module",
                       file_paths=["other/x.py"], evidence=["other/x.py"], confidence="structural")
    index.nodes = index.nodes + [extra_node]

    mermaid = render_mermaid_flow(index, 0)

    assert "module: app" in mermaid
    assert "module: other" not in mermaid
    assert "%% Entrypoint reachability: app" in mermaid


def test_render_mermaid_handles_an_empty_graph_without_crashing():
    index = _fixture_index()
    index.nodes, index.edges = [], []

    mermaid = render_mermaid_graph(index)

    assert "graph LR" in mermaid
    assert "%% Repo:" in mermaid


def test_render_mermaid_escapes_quotes_in_labels():
    index = _fixture_index()
    index.nodes = [Node(id="module:x", label='weird"label', type="module",
                         file_paths=[], evidence=[], confidence="structural")]
    index.edges = []

    mermaid = render_mermaid_graph(index)

    assert "weird'label" in mermaid
    assert 'weird"label' not in mermaid


# ---------- HTML export ----------

def test_render_html_report_is_a_standalone_document_with_no_external_resources():
    html = render_html_report(_fixture_index())

    assert html.startswith("<!doctype html>")
    assert "<style>" in html  # inline CSS, not a <link rel="stylesheet">
    assert "<link" not in html.lower()
    assert "<script" not in html.lower()
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


def test_render_html_report_shows_repo_url_and_commit_sha():
    html = render_html_report(_fixture_index())

    assert "https://github.com/octocat/Hello-World" in html
    assert "abcdef1" in html  # short SHA, same convention as report.py


def test_render_html_report_covers_the_same_sections_as_the_markdown_report():
    html = render_html_report(_fixture_index())

    for heading in (
        "Files &amp; Languages", "Detected Stack", "Entrypoints",
        "Review Findings", "Start Here",
    ):
        assert heading in html


def test_render_html_report_escapes_repo_derived_text():
    index = _fixture_index()
    evil_path = 'evil"><script>alert(1)</script>.py'
    index.files = [FileInfo(path=evil_path, language="Python", size=1, role="entrypoint")]
    index.modules = [Module(
        name="app", file_count=1, key_files=[evil_path],
        has_entrypoint=True, has_manifest=False, description="1 file.",
    )]

    html = render_html_report(index)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


if __name__ == "__main__":
    test_render_mermaid_graph_includes_repo_url_and_commit_as_comments()
    test_render_mermaid_graph_renders_every_node_and_edge()
    test_render_mermaid_flow_scopes_to_the_selected_flow_only()
    test_render_mermaid_handles_an_empty_graph_without_crashing()
    test_render_mermaid_escapes_quotes_in_labels()
    test_render_html_report_is_a_standalone_document_with_no_external_resources()
    test_render_html_report_shows_repo_url_and_commit_sha()
    test_render_html_report_covers_the_same_sections_as_the_markdown_report()
    test_render_html_report_escapes_repo_derived_text()
    print("ok")
