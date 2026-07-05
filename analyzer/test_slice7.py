"""Runnable check for Slice 7: the entrypoint-reachability flow explorer,
derived only from the already-computed graph (Node/Edge) — no new
file-content parsing beyond what `build_graph` already does."""
import subprocess
import tempfile
from pathlib import Path

from analyze import analyze_local_repo


def _git_init_and_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=test", "commit", "-q", "-m", "init"],
        cwd=root, check=True,
    )


def make_two_entrypoint_fixture_repo(root: Path) -> None:
    """`app/main.py` is an entrypoint with real outgoing edges (imports
    `lib`, depends on `requests`); root-level `cli.py` is a second
    entrypoint whose only import (`os`, stdlib) resolves to nothing — its
    module should still get a flow, just one with zero edges."""
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text(
        "from lib import helper\n"
        "import requests\n"
    )
    (root / "lib").mkdir()
    (root / "lib" / "helper.py").write_text("def helper():\n    pass\n")
    (root / "requirements.txt").write_text("requests==2.31.0\n")
    (root / "cli.py").write_text("import os\n")
    _git_init_and_commit(root)


def make_no_entrypoint_fixture_repo(root: Path) -> None:
    (root / "lib").mkdir()
    (root / "lib" / "helper.py").write_text("def helper():\n    pass\n")
    _git_init_and_commit(root)


def make_entrypoint_no_edges_fixture_repo(root: Path) -> None:
    """A single entrypoint with no imports at all: the graph has a node but
    zero edges anywhere, so no flow should be fabricated."""
    (root / "main.py").write_text("print('hello')\n")
    _git_init_and_commit(root)


def test_entrypoint_with_edges_produces_a_flow_that_is_a_real_subset_of_the_graph():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_two_entrypoint_fixture_repo(root)

        index = analyze_local_repo(root)
        node_ids = {n.id for n in index.nodes}
        edge_keys = {(e.source, e.target, e.type) for e in index.edges}

        app_flow = next(f for f in index.flows if f.title == "Entrypoint reachability: app")

        assert app_flow.nodes, "expected at least the starting module node"
        for node in app_flow.nodes:
            assert node.id in node_ids
        for edge in app_flow.edges:
            assert (edge.source, edge.target, edge.type) in edge_keys
        assert any(e.type == "imports" for e in app_flow.edges)
        assert any(e.type == "depends_on" for e in app_flow.edges)
        assert set(app_flow.evidence).issubset({f.path for f in index.files})
        assert app_flow.confidence == "heuristic"


def test_entrypoint_with_no_outgoing_edges_is_labeled_uncertain_not_omitted():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_two_entrypoint_fixture_repo(root)

        index = analyze_local_repo(root)
        root_flow = next(f for f in index.flows if f.title == "Entrypoint reachability: (repo root)")

        assert root_flow.edges == []
        assert "no outgoing" in root_flow.explanation.lower() or "missing" in root_flow.explanation.lower()


def test_no_entrypoints_yields_no_flows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_no_entrypoint_fixture_repo(root)

        index = analyze_local_repo(root)

        assert index.modules and not any(m.has_entrypoint for m in index.modules)
        assert index.flows == []


def test_entrypoint_with_no_edges_anywhere_yields_no_flows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_entrypoint_no_edges_fixture_repo(root)

        index = analyze_local_repo(root)

        assert index.edges == []
        assert index.flows == []


def test_empty_repo_yields_no_flows():
    index = analyze_local_repo(Path(tempfile.mkdtemp()))

    assert index.flows == []


if __name__ == "__main__":
    test_entrypoint_with_edges_produces_a_flow_that_is_a_real_subset_of_the_graph()
    test_entrypoint_with_no_outgoing_edges_is_labeled_uncertain_not_omitted()
    test_no_entrypoints_yields_no_flows()
    test_entrypoint_with_no_edges_anywhere_yields_no_flows()
    test_empty_repo_yields_no_flows()
    print("ok")
