"""Mermaid diagram export (Slice 8): serializes the already-computed
architecture graph, or a single `Flow`'s node/edge subset, into Mermaid
flowchart syntax. No new detection -- purely a text serializer over
`Node`/`Edge` data `analyze.py`'s `build_graph`/`detect_flows` already
produced, kept in its own module so it's testable independent of the web
layer (see `server/main.py`'s `/api/export/mermaid`)."""
from __future__ import annotations

from analyze import Edge, Node, RepoIndex, RepoInfo

# Mermaid flowchart shapes, keyed by our `Node.type`. Anything not listed
# here (shouldn't currently happen -- build_graph only emits "module"/
# "dependency") falls back to a plain rectangle.
_NODE_SHAPE_BY_TYPE = {"module": ("[", "]"), "dependency": ("(", ")")}
_DEFAULT_NODE_SHAPE = ("[", "]")

# "imports" edges are solid, "depends_on" are dashed -- mirrors the same
# visual distinction the live SVG graph view draws (see styles.css).
_EDGE_ARROW_BY_TYPE = {"imports": "-->", "depends_on": "-.->"}
_DEFAULT_EDGE_ARROW = "-->"


def render_mermaid_graph(index: RepoIndex) -> str:
    """The full architecture graph as Mermaid `graph LR` syntax."""
    return _render_mermaid(index.nodes, index.edges, index.repo)


def render_mermaid_flow(index: RepoIndex, flow_index: int) -> str:
    """A single detected `Flow`'s node/edge subset as Mermaid syntax."""
    flow = index.flows[flow_index]
    return _render_mermaid(flow.nodes, flow.edges, index.repo, title=flow.title)


def _render_mermaid(
    nodes: list[Node], edges: list[Edge], repo: RepoInfo, title: str = ""
) -> str:
    safe_ids = {node.id: f"n{i}" for i, node in enumerate(nodes)}
    lines = _header_comment(repo, title)
    lines.append("graph LR")
    lines += [_node_line(node, safe_ids[node.id]) for node in nodes]
    lines += _edge_lines(edges, safe_ids)
    return "\n".join(lines) + "\n"


def _header_comment(repo: RepoInfo, title: str) -> list[str]:
    """Every Mermaid export carries the repo URL + commit SHA as a comment
    (Slice 8: "every export must include repo URL and commit SHA")."""
    lines = [f"%% {title}"] if title else []
    lines.append(f"%% Repo: {repo.url or _repo_label(repo)}")
    lines.append(f"%% Commit: {repo.commit_sha[:7] if repo.commit_sha else 'n/a'}")
    return lines


def _repo_label(repo: RepoInfo) -> str:
    return f"{repo.owner}/{repo.name}" if repo.owner else repo.name


def _node_line(node: Node, safe_id: str) -> str:
    open_shape, close_shape = _NODE_SHAPE_BY_TYPE.get(node.type, _DEFAULT_NODE_SHAPE)
    label = escape_label(f"{node.type}: {node.label}")
    return f'    {safe_id}{open_shape}"{label}"{close_shape}'


def _edge_lines(edges: list[Edge], safe_ids: dict[str, str]) -> list[str]:
    """Every real edge's `source`/`target` is always among `safe_ids` in
    practice (edges only ever reference nodes `analyze.py` itself
    produced), but skip rather than crash on an edge referencing an id that
    wasn't rendered as a node here -- never fabricate a connection."""
    lines = []
    for edge in edges:
        if edge.source not in safe_ids or edge.target not in safe_ids:
            continue
        arrow = _EDGE_ARROW_BY_TYPE.get(edge.type, _DEFAULT_EDGE_ARROW)
        label = escape_label(edge.label)
        lines.append(f'    {safe_ids[edge.source]} {arrow}|"{label}"| {safe_ids[edge.target]}')
    return lines


def escape_label(text: str) -> str:
    """Mermaid quoted-string labels can't contain a literal `"`; swap for a
    plain apostrophe rather than trying to escape it (Mermaid has no
    backslash-escape for quotes inside `"..."` labels)."""
    return text.replace('"', "'")
