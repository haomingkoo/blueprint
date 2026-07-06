> **Superseded — do not execute.** Slice 10 (and Slices 11-14) were already
> implemented, independently of this plan, directly under
> `analyzer/analyze.py` (`cluster_modules`) and
> `.claude/skills/understand-repo/scripts/` — a different file layout than
> this plan specifies (it proposed a separate `analyzer/cluster.py` and
> `analyzer/understand_db.py`, neither of which exist). Kept only as a
> record of the original design intent; see `docs/HANDOFF.md`'s Slice
> 10-14 entries for what actually shipped.

# Understand-Repo Slice 10: Clustering + Skill Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic backbone of the `/understand-repo` skill: cluster Blueprint's existing module graph into subsystems (no LLM), persist one versioned "sweep" per run to SQLite, and ship a thin skill scaffold that invokes it — matching Slice 10 of `docs/issues.md` and `docs/prd-understand-repo.md`.

**Architecture:** A new `analyzer/cluster.py` groups module nodes into subsystems via connected components over the existing `"imports"` edges. A new `analyzer/understand_db.py` persists one sweep (repo metadata, modules, nodes, edges, subsystems) to a SQLite file using only stdlib. A new `analyzer/sweep.py` orchestrates both, writing a new timestamped directory per run under `.understanding/<repo-name>/` and updating a `latest` symlink. A new `.claude/skills/understand-repo/SKILL.md` is a thin wrapper that tells Claude to run `sweep.py` and relay its exact output.

**Tech Stack:** Python 3.12, stdlib only (`sqlite3`, `json`, `datetime`, `argparse`, `pathlib`) — reuses `analyzer/analyze.py`'s existing `analyze_local_repo`, `Node`, `Edge`, `RepoIndex`.

## Global Constraints

- Zero new runtime dependencies — stdlib only, no new entries in any requirements file.
- Python 3.12 target, type hints on every function signature, `from __future__ import annotations` at the top of every new module (matches `analyzer/analyze.py`'s existing convention).
- Line length 88, ruff-clean (`uvx ruff@0.15.20 check analyzer server` must stay clean — see `pyproject.toml`).
- `.understanding/` output is written under this blueprint repo's own tree, **never** inside the repo being swept, and must be gitignored.
- Every run of the sweep creates a **new** timestamped directory; a prior sweep is never overwritten (design: "history over overwrite").
- This slice introduces no new confidence tier — every `Module`/`Node`/`Edge` value persisted keeps its existing `"structural"`/`"heuristic"` confidence exactly as `analyze_local_repo` produced it. The new `"semantic"` tier belongs to Slice 11, not this one.
- Commit messages follow Conventional Commits (`feat(analyzer): ...`), imperative mood, ≤72 char subject line.

---

### Task 1: Module Clustering (`analyzer/cluster.py`)

**Files:**
- Create: `analyzer/cluster.py`
- Test: `analyzer/test_cluster.py`

**Interfaces:**
- Consumes: `analyze.Node` (fields: `id, label, type, file_paths, evidence, confidence`), `analyze.Edge` (fields: `source, target, type, label, evidence, confidence`) — both already exist in `analyzer/analyze.py`.
- Produces: `Subsystem` dataclass (`id: str`, `name: str`, `module_names: list[str]`) and `cluster_modules(nodes: list[Node], edges: list[Edge]) -> list[Subsystem]`, both importable as `from cluster import Subsystem, cluster_modules`. Later tasks in this plan depend on this exact signature.

- [ ] **Step 1: Write the failing test**

Create `analyzer/test_cluster.py`:

```python
"""Runnable check for Slice 10's clustering: connected components over
module->module "imports" edges, independent of any real repo scan (the
graph-to-DB path is covered by test_sweep.py)."""
from analyze import Edge, Node
from cluster import cluster_modules


def _module_node(name: str) -> Node:
    return Node(
        id=f"module:{name}", label=name, type="module",
        file_paths=[], evidence=[], confidence="structural",
    )


def _imports_edge(source: str, target: str) -> Edge:
    return Edge(
        source=f"module:{source}", target=f"module:{target}", type="imports",
        label="imports", evidence=[f"{source}/x.py"], confidence="heuristic",
    )


def test_two_connected_modules_form_one_subsystem():
    nodes = [_module_node("api"), _module_node("lib")]
    edges = [_imports_edge("api", "lib")]

    subsystems = cluster_modules(nodes, edges)

    assert len(subsystems) == 1
    assert subsystems[0].module_names == ["api", "lib"]
    assert subsystems[0].name == "api"


def test_module_with_no_edges_is_its_own_singleton_subsystem():
    nodes = [_module_node("standalone")]

    subsystems = cluster_modules(nodes, [])

    assert len(subsystems) == 1
    assert subsystems[0].module_names == ["standalone"]


def test_two_unconnected_modules_form_two_subsystems():
    nodes = [_module_node("api"), _module_node("worker")]

    subsystems = cluster_modules(nodes, [])

    assert len(subsystems) == 2
    assert {s.name for s in subsystems} == {"api", "worker"}


def test_depends_on_edges_are_ignored_for_clustering():
    """A module->manifest depends_on edge must never merge two modules --
    only "imports" module->module edges count toward a cluster."""
    nodes = [_module_node("api"), _module_node("lib")]
    edges = [
        Edge(
            source="module:api", target="manifest:package.json", type="depends_on",
            label="depends on", evidence=["api/x.py"], confidence="heuristic",
        ),
    ]

    subsystems = cluster_modules(nodes, edges)

    assert len(subsystems) == 2


def test_a_three_module_chain_forms_one_subsystem():
    nodes = [_module_node("api"), _module_node("lib"), _module_node("core")]
    edges = [_imports_edge("api", "lib"), _imports_edge("lib", "core")]

    subsystems = cluster_modules(nodes, edges)

    assert len(subsystems) == 1
    assert subsystems[0].module_names == ["api", "core", "lib"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest analyzer/test_cluster.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cluster'`

- [ ] **Step 3: Write the implementation**

Create `analyzer/cluster.py`:

```python
"""Slice 10: group module nodes into subsystems, no LLM involved. A
subsystem is a connected component over the existing "imports"
module-to-module edges `build_graph` already computed in analyze.py --
deterministic and reproducible, the structural backbone the later semantic
slices (11-13) sit on top of."""
from __future__ import annotations

from dataclasses import dataclass

from analyze import Edge, Node


@dataclass
class Subsystem:
    id: str
    name: str
    module_names: list[str]


def cluster_modules(nodes: list[Node], edges: list[Edge]) -> list[Subsystem]:
    """Connected components over module->module "imports" edges only --
    "depends_on" edges (module->manifest) never merge two modules. A module
    with no inter-module edges becomes its own singleton subsystem, never
    dropped."""
    module_names = [n.id.removeprefix("module:") for n in nodes if n.type == "module"]
    adjacency: dict[str, set[str]] = {name: set() for name in module_names}
    for e in edges:
        if e.type != "imports":
            continue
        source = e.source.removeprefix("module:")
        target = e.target.removeprefix("module:")
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)

    seen: set[str] = set()
    components: list[list[str]] = []
    for name in module_names:
        if name in seen:
            continue
        components.append(sorted(_walk_component(name, adjacency, seen)))

    return [
        Subsystem(id=f"subsystem:{component[0]}", name=component[0], module_names=component)
        for component in sorted(components, key=lambda c: c[0])
    ]


def _walk_component(start: str, adjacency: dict[str, set[str]], seen: set[str]) -> set[str]:
    stack = [start]
    component: set[str] = set()
    while stack:
        current = stack.pop()
        if current in component:
            continue
        component.add(current)
        seen.add(current)
        stack.extend(adjacency[current] - component)
    return component
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest analyzer/test_cluster.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add analyzer/cluster.py analyzer/test_cluster.py
git commit -m "feat(analyzer): add module clustering for subsystem detection"
```

---

### Task 2: Sweep Persistence (`analyzer/understand_db.py`)

**Files:**
- Create: `analyzer/understand_db.py`
- Test: `analyzer/test_understand_db.py`

**Interfaces:**
- Consumes: `analyze.RepoIndex` (existing), `cluster.Subsystem` (Task 1).
- Produces: `open_db(db_path: Path) -> sqlite3.Connection` and `write_sweep(conn: sqlite3.Connection, index: RepoIndex, subsystems: list[Subsystem], repo_path: Path, started_at: str, finished_at: str) -> int` (returns the new `sweep_id`), both importable as `from understand_db import open_db, write_sweep`. Task 3 depends on this exact signature.

- [ ] **Step 1: Write the failing test**

Create `analyzer/test_understand_db.py`:

```python
"""Runnable check for Slice 10's SQLite persistence: schema creation +
write_sweep, using small fixture data written to a real temp-file db (the
full real-repo path is covered by test_sweep.py)."""
import json

from analyze import FileInfo, Module, Node, RepoIndex, RepoInfo
from cluster import Subsystem
from understand_db import open_db, write_sweep


def _fixture_index() -> RepoIndex:
    return RepoIndex(
        repo=RepoInfo(
            provider="github", owner="octocat", name="Hello-World",
            branch="main", commit_sha="abc1234", url="https://github.com/octocat/Hello-World",
        ),
        files=[FileInfo(path="README", language="Markdown", size=10, role="docs")],
        language_counts={"Markdown": 1},
        modules=[Module(
            name="(repo root)", file_count=1, key_files=["README"],
            has_entrypoint=False, has_manifest=False, description="fact. inference.",
        )],
        nodes=[Node(
            id="module:(repo root)", label="(repo root)", type="module",
            file_paths=["README"], evidence=["README"], confidence="structural",
        )],
        edges=[],
    )


def test_write_sweep_persists_modules_nodes_and_subsystems(tmp_path):
    conn = open_db(tmp_path / "understanding.db")
    index = _fixture_index()
    subsystems = [Subsystem(id="subsystem:(repo root)", name="(repo root)", module_names=["(repo root)"])]

    sweep_id = write_sweep(conn, index, subsystems, tmp_path, "2026-07-06T00:00:00Z", "2026-07-06T00:00:05Z")

    modules = conn.execute("SELECT name, file_count FROM modules WHERE sweep_id = ?", (sweep_id,)).fetchall()
    assert modules == [("(repo root)", 1)]

    nodes = conn.execute("SELECT id, type FROM nodes WHERE sweep_id = ?", (sweep_id,)).fetchall()
    assert nodes == [("module:(repo root)", "module")]

    subsystem_rows = conn.execute("SELECT id, name FROM subsystems WHERE sweep_id = ?", (sweep_id,)).fetchall()
    assert subsystem_rows == [("subsystem:(repo root)", "(repo root)")]

    membership = conn.execute(
        "SELECT module_name, subsystem_id FROM module_subsystem WHERE sweep_id = ?", (sweep_id,)
    ).fetchall()
    assert membership == [("(repo root)", "subsystem:(repo root)")]


def test_write_sweep_stores_key_files_as_json(tmp_path):
    conn = open_db(tmp_path / "understanding.db")
    index = _fixture_index()

    sweep_id = write_sweep(conn, index, [], tmp_path, "2026-07-06T00:00:00Z", "2026-07-06T00:00:05Z")

    row = conn.execute("SELECT key_files FROM modules WHERE sweep_id = ?", (sweep_id,)).fetchone()
    assert json.loads(row[0]) == ["README"]


def test_two_sweeps_in_the_same_db_stay_independent(tmp_path):
    conn = open_db(tmp_path / "understanding.db")
    index = _fixture_index()

    sweep_id_1 = write_sweep(conn, index, [], tmp_path, "2026-07-06T00:00:00Z", "2026-07-06T00:00:05Z")
    sweep_id_2 = write_sweep(conn, index, [], tmp_path, "2026-07-06T01:00:00Z", "2026-07-06T01:00:05Z")

    assert sweep_id_1 != sweep_id_2
    count = conn.execute("SELECT COUNT(*) FROM modules WHERE sweep_id = ?", (sweep_id_1,)).fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest analyzer/test_understand_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'understand_db'`

- [ ] **Step 3: Write the implementation**

Create `analyzer/understand_db.py`:

```python
"""Slice 10: SQLite persistence for one sweep -- stdlib `sqlite3` and
`json` only, no new dependency. Schema matches the shapes in
docs/prd-understand-repo.md's MVP Data Model; the `subsystems.narrative`
column stays empty until Slice 12 populates it (no migration needed later,
since the column already exists)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from analyze import RepoIndex
from cluster import Subsystem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sweeps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    branch TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS modules (
    sweep_id INTEGER NOT NULL REFERENCES sweeps(id),
    name TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    key_files TEXT NOT NULL,
    has_entrypoint INTEGER NOT NULL,
    has_manifest INTEGER NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    sweep_id INTEGER NOT NULL REFERENCES sweeps(id),
    id TEXT NOT NULL,
    label TEXT NOT NULL,
    type TEXT NOT NULL,
    file_paths TEXT NOT NULL,
    evidence TEXT NOT NULL,
    confidence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    sweep_id INTEGER NOT NULL REFERENCES sweeps(id),
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    type TEXT NOT NULL,
    label TEXT NOT NULL,
    evidence TEXT NOT NULL,
    confidence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subsystems (
    sweep_id INTEGER NOT NULL REFERENCES sweeps(id),
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    narrative TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS module_subsystem (
    sweep_id INTEGER NOT NULL REFERENCES sweeps(id),
    module_name TEXT NOT NULL,
    subsystem_id TEXT NOT NULL
);
"""


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def write_sweep(
    conn: sqlite3.Connection,
    index: RepoIndex,
    subsystems: list[Subsystem],
    repo_path: Path,
    started_at: str,
    finished_at: str,
) -> int:
    """Inserts one sweep's worth of rows and returns the new sweep_id."""
    cursor = conn.execute(
        "INSERT INTO sweeps (repo_path, repo_name, commit_sha, branch, started_at, finished_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(repo_path), index.repo.name, index.repo.commit_sha, index.repo.branch, started_at, finished_at),
    )
    sweep_id = cursor.lastrowid
    assert sweep_id is not None

    conn.executemany(
        "INSERT INTO modules (sweep_id, name, file_count, key_files, has_entrypoint, has_manifest, description) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (sweep_id, m.name, m.file_count, json.dumps(m.key_files), m.has_entrypoint, m.has_manifest, m.description)
            for m in index.modules
        ],
    )
    conn.executemany(
        "INSERT INTO nodes (sweep_id, id, label, type, file_paths, evidence, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (sweep_id, n.id, n.label, n.type, json.dumps(n.file_paths), json.dumps(n.evidence), n.confidence)
            for n in index.nodes
        ],
    )
    conn.executemany(
        "INSERT INTO edges (sweep_id, source, target, type, label, evidence, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (sweep_id, e.source, e.target, e.type, e.label, json.dumps(e.evidence), e.confidence)
            for e in index.edges
        ],
    )
    conn.executemany(
        "INSERT INTO subsystems (sweep_id, id, name, narrative) VALUES (?, ?, ?, '')",
        [(sweep_id, s.id, s.name) for s in subsystems],
    )
    conn.executemany(
        "INSERT INTO module_subsystem (sweep_id, module_name, subsystem_id) VALUES (?, ?, ?)",
        [(sweep_id, name, s.id) for s in subsystems for name in s.module_names],
    )
    conn.commit()
    return sweep_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest analyzer/test_understand_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add analyzer/understand_db.py analyzer/test_understand_db.py
git commit -m "feat(analyzer): add SQLite persistence for repo sweeps"
```

---

### Task 3: Sweep Orchestrator + CLI (`analyzer/sweep.py`)

**Files:**
- Create: `analyzer/sweep.py`
- Test: `analyzer/test_sweep.py`
- Modify: `.gitignore` (add `.understanding/`)

**Interfaces:**
- Consumes: `analyze.analyze_local_repo` (existing), `cluster.cluster_modules`/`cluster.Subsystem` (Task 1), `understand_db.open_db`/`understand_db.write_sweep` (Task 2).
- Produces: `run_sweep(repo_path: Path, understanding_root: Path) -> tuple[Path, list[Subsystem]]` and a `main()` CLI entrypoint, importable as `from sweep import run_sweep`. Task 4's skill instructions depend on `main()`'s exact stdout format defined below.

- [ ] **Step 1: Write the failing test**

Create `analyzer/test_sweep.py`:

```python
"""Runnable check for Slice 10's sweep orchestrator: a real fixture repo on
disk -> a versioned sweep directory with a working `latest` pointer and a
populated SQLite db. Same real-filesystem-fixture convention as
test_slice6.py/test_slice7.py."""
import subprocess
from pathlib import Path

from sweep import run_sweep
from understand_db import open_db


def _git_init_and_commit(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=test", "commit", "-q", "-m", "init"],
        cwd=root, check=True,
    )


def make_two_module_fixture_repo(root: Path) -> None:
    (root / "api").mkdir()
    (root / "api" / "main.py").write_text("from lib import helper\n")
    (root / "lib").mkdir()
    (root / "lib" / "helper.py").write_text("def helper():\n    pass\n")
    _git_init_and_commit(root)


def test_run_sweep_writes_a_db_with_the_expected_subsystem(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    make_two_module_fixture_repo(repo_root)
    understanding_root = tmp_path / "understanding"

    sweep_dir, subsystems = run_sweep(repo_root, understanding_root)

    assert sweep_dir.exists()
    assert (sweep_dir / "understanding.db").exists()
    assert len(subsystems) == 1
    assert subsystems[0].module_names == ["api", "lib"]

    conn = open_db(sweep_dir / "understanding.db")
    try:
        rows = conn.execute("SELECT name FROM modules").fetchall()
    finally:
        conn.close()
    assert {r[0] for r in rows} == {"api", "lib"}


def test_run_sweep_updates_the_latest_pointer_on_rerun(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    make_two_module_fixture_repo(repo_root)
    understanding_root = tmp_path / "understanding"

    first_dir, _ = run_sweep(repo_root, understanding_root)
    second_dir, _ = run_sweep(repo_root, understanding_root)

    latest = understanding_root / "repo" / "latest"
    assert first_dir != second_dir
    assert latest.resolve() == second_dir.resolve()


def test_run_sweep_handles_a_repo_with_no_git_history(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "main.py").write_text("print('hi')\n")
    understanding_root = tmp_path / "understanding"

    sweep_dir, subsystems = run_sweep(repo_root, understanding_root)

    assert "nogit" in sweep_dir.name
    assert len(subsystems) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest analyzer/test_sweep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sweep'`

- [ ] **Step 3: Write the implementation**

Create `analyzer/sweep.py`:

```python
"""Slice 10 entrypoint: local repo path -> a versioned "sweep" (structural
analysis + module clustering, persisted to SQLite) under
`.understanding/<repo-name>/<timestamp>-<short-sha>/`. No semantic layer
yet -- see docs/prd-understand-repo.md for the full build order."""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from analyze import analyze_local_repo
from cluster import Subsystem, cluster_modules
from understand_db import open_db, write_sweep

_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def run_sweep(repo_path: Path, understanding_root: Path) -> tuple[Path, list[Subsystem]]:
    """Runs the structural pass + clustering, writes a new timestamped
    sweep directory under `understanding_root`, updates its `latest`
    pointer, and returns the sweep directory plus its subsystems."""
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    index = analyze_local_repo(repo_path)
    subsystems = cluster_modules(index.nodes, index.edges)
    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    short_sha = index.repo.commit_sha[:7] if index.repo.commit_sha else "nogit"
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(_TIMESTAMP_FORMAT)
    repo_name = index.repo.name or repo_path.name
    repo_root_dir = understanding_root / repo_name
    sweep_dir = repo_root_dir / f"{timestamp}-{short_sha}"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    conn = open_db(sweep_dir / "understanding.db")
    try:
        write_sweep(conn, index, subsystems, repo_path, started_at, finished_at)
    finally:
        conn.close()

    _update_latest_pointer(repo_root_dir, sweep_dir)
    return sweep_dir, subsystems


def _update_latest_pointer(repo_root_dir: Path, sweep_dir: Path) -> None:
    latest = repo_root_dir / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(sweep_dir.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep a local repo: structural analysis + module clustering")
    parser.add_argument("repo_path", help="Path to a local repo to sweep")
    parser.add_argument(
        "--output-root", default=None,
        help="Where to write sweep directories (default: <blueprint repo>/.understanding)",
    )
    args = parser.parse_args()

    default_root = Path(__file__).resolve().parent.parent / ".understanding"
    understanding_root = Path(args.output_root) if args.output_root else default_root
    repo_path = Path(args.repo_path).resolve()

    sweep_dir, subsystems = run_sweep(repo_path, understanding_root)

    print(f"Swept {repo_path} -> {sweep_dir}")
    print(f"{len(subsystems)} subsystem(s) detected:")
    for s in subsystems:
        print(f"- {s.name}: {', '.join(s.module_names)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest analyzer/test_sweep.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Add `.understanding/` to `.gitignore`**

Open `.gitignore` and add a new line at the end:

```
.understanding/
```

- [ ] **Step 6: Manually verify the CLI end-to-end against this repo**

Run: `python3 analyzer/sweep.py . --output-root /tmp/blueprint-sweep-check`
Expected: prints `Swept <path> -> /tmp/blueprint-sweep-check/blueprint/<timestamp>-<sha>` followed by a non-empty `N subsystem(s) detected:` list. Confirms the CLI works against a real repo, not just fixtures.

- [ ] **Step 7: Commit**

```bash
git add analyzer/sweep.py analyzer/test_sweep.py .gitignore
git commit -m "feat(analyzer): add sweep orchestrator with versioned output"
```

---

### Task 4: Skill Scaffold (`.claude/skills/understand-repo/SKILL.md`)

**Files:**
- Create: `.claude/skills/understand-repo/SKILL.md`

**Interfaces:**
- Consumes: `analyzer/sweep.py`'s `main()` CLI, specifically its stdout format from Task 3 (`Swept <path> -> <dir>`, then `N subsystem(s) detected:`, then one `- <name>: <modules>` line per subsystem).
- Produces: the `/understand-repo` slash command, invocable from within this blueprint repo.

- [ ] **Step 1: Create the skill file**

Create `.claude/skills/understand-repo/SKILL.md`:

```markdown
---
name: understand-repo
description: Sweep a local repo path with Blueprint's analyzer and group its modules into subsystems via the real import graph -- no LLM interpretation yet (that's a later slice). Use when the user asks to "understand this repo", "sweep this codebase", or invokes /understand-repo.
---

# Understand Repo

Runs Blueprint's structural analyzer against a local repo path, clusters its
modules into subsystems using the real import graph (connected components,
no guessing), and persists the result as a new versioned sweep.

## Steps

1. Take the repo path from the user's message (the argument after
   `/understand-repo`). If missing, ask for it.
2. Run, from this blueprint repo's root:
   ```
   python3 analyzer/sweep.py <repo_path>
   ```
3. Report back to the user:
   - The sweep directory the command printed.
   - The list of detected subsystems and their member modules, exactly as
     printed by the command -- don't rephrase or add interpretation, this
     slice is structural-only (no semantic layer yet).

## Notes

- This is Slice 10 of `docs/prd-understand-repo.md` -- clustering and
  persistence only. Later slices add verified per-module semantic
  summaries (Slice 11), a subsystem narrative (Slice 12), and a browsable
  HTML site (Slice 13); none of that exists yet, so don't invent it when
  reporting results.
- Output lives under this blueprint repo's own `.understanding/` directory
  (gitignored), never inside the swept repo.
```

- [ ] **Step 2: Manually verify the skill is discovered**

Start a new Claude Code session in this repo and check that `understand-repo` appears in the available skills list (or run `/understand-repo` directly against a small repo path and confirm it runs `analyzer/sweep.py` and relays its output as instructed above).

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/understand-repo/SKILL.md
git commit -m "feat: add /understand-repo skill scaffold for Slice 10"
```

---

### Task 5: Full Verification Sweep

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m pytest analyzer server -q`
Expected: all tests pass, including the 11 new tests from Tasks 1-3 (5 + 3 + 3).

- [ ] **Step 2: Run ruff**

Run: `uvx ruff@0.15.20 check analyzer server`
Expected: `All checks passed!`

- [ ] **Step 3: Run ty**

Run: `uvx --with-requirements server/requirements.txt ty@0.0.56 check`
Expected: the same 2 pre-existing baseline diagnostics noted in every prior slice's handoff (both in Slice 2's manifest parsers) — no new diagnostics from `cluster.py`/`understand_db.py`/`sweep.py`.

- [ ] **Step 4: Run compileall**

Run: `python3 -m compileall -q analyzer server`
Expected: no output, exit code 0.

- [ ] **Step 5: Append a Slice 10 handoff entry to `docs/HANDOFF.md`**

Follow the existing handoff format (see the Slice 9 entry) — summarize what shipped, what was verified, and note that Slice 11 (verified per-module semantic summaries) is next. Commit this alongside the verification results:

```bash
git add docs/HANDOFF.md
git commit -m "docs: log Slice 10 handoff"
```
