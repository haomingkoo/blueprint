"""Runnable check for Slice 10: clustering module nodes into subsystems via
connected components over "imports" edges only -- no LLM, no file scanning,
pure graph traversal over Node/Edge already produced by build_graph."""
from analyze import Edge, Node, cluster_modules


def _module_node(name: str) -> Node:
    return Node(id=f"module:{name}", label=name, type="module", file_paths=[], evidence=[], confidence="structural")


def _manifest_node(name: str) -> Node:
    return Node(id=f"manifest:{name}", label=name, type="dependency", file_paths=[], evidence=[], confidence="structural")


def _import_edge(source: str, target: str) -> Edge:
    return Edge(
        source=f"module:{source}", target=f"module:{target}",
        type="imports", label="imports", evidence=[], confidence="heuristic",
    )


def test_connected_modules_form_one_subsystem():
    nodes = [_module_node("app"), _module_node("lib")]
    edges = [_import_edge("app", "lib")]

    subsystems = cluster_modules(nodes, edges)

    assert len(subsystems) == 1
    assert sorted(subsystems[0].module_names) == ["app", "lib"]


def test_module_with_no_inter_module_edges_is_its_own_singleton():
    nodes = [_module_node("app"), _module_node("standalone")]

    subsystems = cluster_modules(nodes, [])

    assert len(subsystems) == 2
    assert all(len(s.module_names) == 1 for s in subsystems)
    assert {s.module_names[0] for s in subsystems} == {"app", "standalone"}


def test_depends_on_edges_never_merge_modules_into_a_subsystem():
    """A "depends_on" edge targets a manifest/dependency node, not another
    module -- clustering must only ever follow "imports" edges."""
    nodes = [_module_node("app"), _manifest_node("requirements.txt")]
    edges = [Edge(
        source="module:app", target="manifest:requirements.txt",
        type="depends_on", label="depends on", evidence=[], confidence="heuristic",
    )]

    subsystems = cluster_modules(nodes, edges)

    assert len(subsystems) == 1
    assert subsystems[0].module_names == ["app"]


def test_transitive_chain_forms_one_subsystem():
    nodes = [_module_node("a"), _module_node("b"), _module_node("c")]
    edges = [_import_edge("a", "b"), _import_edge("b", "c")]

    subsystems = cluster_modules(nodes, edges)

    assert len(subsystems) == 1
    assert sorted(subsystems[0].module_names) == ["a", "b", "c"]


def test_no_module_nodes_yields_no_subsystems():
    assert cluster_modules([], []) == []


if __name__ == "__main__":
    test_connected_modules_form_one_subsystem()
    test_module_with_no_inter_module_edges_is_its_own_singleton()
    test_depends_on_edges_never_merge_modules_into_a_subsystem()
    test_transitive_chain_forms_one_subsystem()
    test_no_module_nodes_yields_no_subsystems()
    print("ok")
