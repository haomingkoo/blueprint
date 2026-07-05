"""Runnable check for Slice 6: the architecture graph (Node/Edge) derived
from modules/manifests plus cheap regex-based import scanning."""
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


def make_python_graph_fixture_repo(root: Path) -> None:
    """`app/main.py` imports `lib` (a real module, internal edge) and
    `requests` (a real dependency in requirements.txt, external edge), plus
    an import that resolves to neither — must not fabricate an edge."""
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text(
        "from lib import helper\n"
        "import requests\n"
        "import totally_unknown_package\n"
    )

    (root / "lib").mkdir()
    (root / "lib" / "helper.py").write_text("def helper():\n    pass\n")

    (root / "requirements.txt").write_text("requests==2.31.0\n")
    _git_init_and_commit(root)


def make_js_graph_fixture_repo(root: Path) -> None:
    """`src/index.js` imports a sibling module (`utils/`) via a relative
    path, and an npm dependency (`left-pad`) declared in package.json."""
    (root / "src").mkdir()
    (root / "src" / "index.js").write_text(
        "import { format } from '../utils/format';\n"
        "const leftPad = require('left-pad');\n"
    )

    (root / "utils").mkdir()
    (root / "utils" / "format.js").write_text("module.exports = {};\n")

    (root / "package.json").write_text(
        '{"name": "fixture", "dependencies": {"left-pad": "^1.3.0"}}\n'
    )
    _git_init_and_commit(root)


def test_module_and_manifest_nodes_have_real_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_python_graph_fixture_repo(root)

        index = analyze_local_repo(root)
        real_paths = {f.path for f in index.files}

        node_ids = {n.id for n in index.nodes}
        assert "module:app" in node_ids
        assert "module:lib" in node_ids
        assert "manifest:requirements.txt" in node_ids

        for node in index.nodes:
            assert node.evidence, f"{node.id} has no evidence"
            assert set(node.evidence).issubset(real_paths)
            assert node.confidence


def test_python_internal_import_edge_is_detected_with_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_python_graph_fixture_repo(root)

        index = analyze_local_repo(root)

        internal_edges = [e for e in index.edges if e.type == "imports"]
        assert any(
            e.source == "module:app" and e.target == "module:lib" and "app/main.py" in e.evidence
            for e in internal_edges
        )


def test_python_external_dependency_edge_is_detected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_python_graph_fixture_repo(root)

        index = analyze_local_repo(root)

        dep_edges = [e for e in index.edges if e.type == "depends_on"]
        assert any(
            e.source == "module:app" and e.target == "manifest:requirements.txt"
            for e in dep_edges
        )


def test_unresolvable_import_does_not_fabricate_an_edge():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_python_graph_fixture_repo(root)

        index = analyze_local_repo(root)

        targets = {e.target for e in index.edges}
        assert not any("totally_unknown_package" in t for t in targets)


def test_js_relative_and_npm_dependency_edges_are_detected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_js_graph_fixture_repo(root)

        index = analyze_local_repo(root)

        assert any(
            e.source == "module:src" and e.target == "module:utils" and e.type == "imports"
            for e in index.edges
        )
        assert any(
            e.source == "module:src"
            and e.target == "manifest:package.json"
            and e.type == "depends_on"
            for e in index.edges
        )


def test_every_edge_evidence_path_is_a_real_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_python_graph_fixture_repo(root)

        index = analyze_local_repo(root)
        real_paths = {f.path for f in index.files}

        for edge in index.edges:
            assert edge.evidence, f"edge {edge.source}->{edge.target} has no evidence"
            assert set(edge.evidence).issubset(real_paths)
            assert edge.confidence == "heuristic"


def test_empty_repo_yields_no_nodes_or_edges():
    index = analyze_local_repo(Path(tempfile.mkdtemp()))

    assert index.nodes == []
    assert index.edges == []


if __name__ == "__main__":
    test_module_and_manifest_nodes_have_real_evidence()
    test_python_internal_import_edge_is_detected_with_evidence()
    test_python_external_dependency_edge_is_detected()
    test_unresolvable_import_does_not_fabricate_an_edge()
    test_js_relative_and_npm_dependency_edges_are_detected()
    test_every_edge_evidence_path_is_a_real_file()
    test_empty_repo_yields_no_nodes_or_edges()
    print("ok")
