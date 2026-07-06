"""Analyze a public GitHub repo (or local path) into structured JSON facts.

Issue 1 built Repo, File, and language-count facts. Issue 2 adds manifest
detection (package.json, pyproject.toml, requirements.txt, setup.py) and
per-file role classification (entrypoint/test/config/docs/unclassified).
Issue 3 adds evidence-backed review `Finding`s (missing test coverage,
config/secrets risk, dependency risk), derived only from files/roles/
manifests already collected above — no new file-content scanning.
Slice 4 groups files into `Module`s (directory-based heuristic) with a
"start here" description per module and a suggested read order, again
derived only from files/roles/manifests already collected above.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", "venv", ".venv",
    "__pycache__", "coverage", ".pytest_cache",
}

LANGUAGE_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".rb": "Ruby",
    ".md": "Markdown", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sh": "Shell",
}

MANIFEST_FILENAMES = {"package.json", "pyproject.toml", "requirements.txt", "setup.py"}

CONFIG_FILENAMES = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".env", ".env.example",
    "tsconfig.json", ".eslintrc", ".eslintrc.json", ".eslintrc.js", "Makefile",
    ".gitignore", "tox.ini", "pytest.ini",
}

ENTRYPOINT_FILENAMES = {
    "main.py", "app.py", "cli.py", "__main__.py", "manage.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "server.ts",
    "app.js", "app.ts",
}

DOCS_FILENAME_PREFIXES = ("README", "CHANGELOG", "LICENSE", "CONTRIBUTING", "CODE_OF_CONDUCT")

TEST_FILE_SUFFIXES = (
    ".test.js", ".test.ts", ".test.jsx", ".test.tsx",
    ".spec.js", ".spec.ts", ".spec.jsx", ".spec.tsx",
)

TEST_DIR_NAMES = {"tests", "test", "__tests__"}

# A manifest listing this many dependencies or more is flagged as a large,
# harder-to-audit dependency surface. Heuristic threshold, not a hard limit.
LARGE_DEPENDENCY_THRESHOLD = 30

# Manifest kinds whose `dependencies` strings retain the original version
# specifier (e.g. "flask==2.0.1"), so "no pinned versions" is checkable.
# npm's `dependencies` only keeps package names (see _parse_package_json),
# and pyproject's Poetry branch does the same, so neither is included here —
# claiming "unpinned" for those would not be backed by real evidence.
PIN_CHECKABLE_MANIFEST_KINDS = {"python-requirements", "python-setuptools"}

VERSION_PIN_MARKERS = ("==", ">=", "<=", "~=", "!=", ">", "<")

# Display name for files that sit directly at the repo root (no containing
# top-level directory to group them by).
ROOT_MODULE_NAME = "(repo root)"

# Cap how many files are listed as "key files" per module, so the report
# stays readable for directories with many files.
MAX_KEY_FILES_PER_MODULE = 5

# Directory-name -> inferred purpose. Naming-only heuristic evidence: matching
# a name here is an inference about intent, never a verified fact about the
# code's actual behavior.
INFERRED_MODULE_PURPOSE = {
    "test": "test suite", "tests": "test suite", "__tests__": "test suite",
    "api": "API layer", "app": "main application code", "src": "primary source code",
    "lib": "shared library code", "libs": "shared library code",
    "utils": "shared utility code", "helpers": "shared utility code",
    "models": "data models", "views": "view layer", "controllers": "controllers",
    "components": "UI components", "pages": "page/route definitions",
    "routes": "route definitions", "docs": "documentation", "doc": "documentation",
    "config": "configuration", "scripts": "scripts/tooling",
    "public": "static assets", "static": "static assets", "assets": "static assets",
    "cli": "command-line interface", "core": "core/shared logic",
}


@dataclass
class RepoInfo:
    provider: str
    owner: str
    name: str
    branch: str
    commit_sha: str
    url: str


@dataclass
class FileInfo:
    path: str
    language: str
    size: int
    role: str = "unclassified"


@dataclass
class Manifest:
    path: str
    kind: str
    name: str
    dependencies: list[str]
    scripts: dict[str, str]


@dataclass
class Finding:
    severity: str
    category: str
    title: str
    evidence: list[str]
    explanation: str
    recommendation: str
    confidence: str


@dataclass
class Module:
    name: str
    file_count: int
    key_files: list[str]
    has_entrypoint: bool
    has_manifest: bool
    description: str


@dataclass
class Node:
    """A node in the architecture graph (PRD MVP Data Model). Slice 6 only
    emits two node types: `"module"` (one per `Module`) and `"dependency"`
    (one per parsed `Manifest`) — see `build_graph`."""
    id: str
    label: str
    type: str
    file_paths: list[str]
    evidence: list[str]
    confidence: str


@dataclass
class Edge:
    """An edge in the architecture graph. Slice 6 only emits `"imports"`
    (module -> module) and `"depends_on"` (module -> dependency) edges,
    detected by cheap regex import scanning — see `build_graph`."""
    source: str
    target: str
    type: str
    label: str
    evidence: list[str]
    confidence: str


@dataclass
class Flow:
    """One traced flow through the architecture graph (PRD MVP Data Model).
    Slice 7 emits exactly one flow type: an entrypoint reachability trace —
    starting at the module containing an entrypoint file, everything
    reachable via the already-detected `imports`/`depends_on` edges (see
    `build_graph`, `detect_flows`). `nodes`/`edges` are always a real subset
    of `RepoIndex.nodes`/`.edges` — no new file-content parsing, nothing
    fabricated. `confidence` mirrors `EDGE_CONFIDENCE`: a flow can never be
    more certain than the (heuristic) edges it's traced from."""
    title: str
    nodes: list[Node]
    edges: list[Edge]
    explanation: str
    evidence: list[str]
    confidence: str


@dataclass
class RepoIndex:
    repo: RepoInfo
    files: list[FileInfo]
    language_counts: dict[str, int]
    manifests: list[Manifest] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    modules: list[Module] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)


def parse_github_url(url: str) -> tuple[str, str]:
    owner, name = url.rstrip("/").removesuffix(".git").split("/")[-2:]
    return owner, name


def clone_repo(url: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)], check=True, capture_output=True
    )


def _git(repo_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def scan_files(repo_path: Path) -> list[FileInfo]:
    files = []
    for path in sorted(repo_path.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_path)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        language = LANGUAGE_BY_EXT.get(path.suffix, "Other")
        files.append(FileInfo(
            path=str(rel), language=language, size=path.stat().st_size,
            role=classify_role(rel),
        ))
    return files


def classify_role(rel_path: Path) -> str:
    """Mark a file's likely role from its path alone (evidence = the path itself)."""
    if rel_path.name in MANIFEST_FILENAMES or rel_path.name in CONFIG_FILENAMES:
        return "config"
    if _is_test_file(rel_path):
        return "test"
    if _is_docs_file(rel_path):
        return "docs"
    if rel_path.name in ENTRYPOINT_FILENAMES:
        return "entrypoint"
    return "unclassified"


def _is_test_file(rel_path: Path) -> bool:
    name = rel_path.name
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith(TEST_FILE_SUFFIXES):
        return True
    if rel_path.stem in {"test", "tests"}:
        return True
    return any(part in TEST_DIR_NAMES for part in rel_path.parts[:-1])


def _is_docs_file(rel_path: Path) -> bool:
    if rel_path.suffix in {".md", ".rst"}:
        return True
    if "docs" in rel_path.parts[:-1]:
        return True
    return rel_path.name.upper().startswith(DOCS_FILENAME_PREFIXES)


def extract_manifests(repo_path: Path, files: list[FileInfo]) -> list[Manifest]:
    """Parse the manifest files present in `files`. Best-effort: a malformed
    manifest is still reported (path + kind) with empty deps/scripts rather
    than crashing the whole analysis."""
    parsers = {
        "package.json": _parse_package_json,
        "pyproject.toml": _parse_pyproject_toml,
        "requirements.txt": _parse_requirements_txt,
        "setup.py": _parse_setup_py,
    }
    manifests = []
    for f in files:
        parser = parsers.get(Path(f.path).name)
        if parser is not None:
            manifests.append(parser(repo_path / f.path, f.path))
    return manifests


def _parse_package_json(abs_path: Path, rel_path: str) -> Manifest:
    try:
        data = json.loads(abs_path.read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    dependencies = sorted({**data.get("dependencies", {}), **data.get("devDependencies", {})})
    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    return Manifest(
        path=rel_path, kind="npm", name=data.get("name", ""),
        dependencies=dependencies, scripts=scripts,
    )


def _parse_pyproject_toml(abs_path: Path, rel_path: str) -> Manifest:
    try:
        data = tomllib.loads(abs_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    project = data.get("project", {})
    poetry = data.get("tool", {}).get("poetry", {})
    dependencies = list(project.get("dependencies", [])) or sorted(
        name for name in poetry.get("dependencies", {}) if name != "python"
    )
    scripts = project.get("scripts") or poetry.get("scripts") or {}
    name = project.get("name") or poetry.get("name") or ""
    return Manifest(
        path=rel_path, kind="python-pyproject", name=name,
        dependencies=dependencies, scripts=scripts,
    )


def _parse_requirements_txt(abs_path: Path, rel_path: str) -> Manifest:
    try:
        lines = abs_path.read_text().splitlines()
    except OSError:
        lines = []
    dependencies = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    return Manifest(path=rel_path, kind="python-requirements", name="", dependencies=dependencies, scripts={})


def _parse_setup_py(abs_path: Path, rel_path: str) -> Manifest:
    name, dependencies = "", []
    try:
        tree = ast.parse(abs_path.read_text())
        call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and _is_setup_call(node))
        name, dependencies = _setup_call_kwargs(call)
    except (OSError, SyntaxError, StopIteration):
        pass
    return Manifest(path=rel_path, kind="python-setuptools", name=name, dependencies=dependencies, scripts={})


def _is_setup_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "setup"
    return isinstance(func, ast.Attribute) and func.attr == "setup"


def _setup_call_kwargs(call: ast.Call) -> tuple[str, list[str]]:
    name, dependencies = "", []
    for kw in call.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            name = kw.value.value
        if kw.arg == "install_requires" and isinstance(kw.value, ast.List):
            dependencies = [elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)]
    return name, dependencies


def generate_findings(files: list[FileInfo], manifests: list[Manifest]) -> list[Finding]:
    """Evidence-backed review findings, derived only from already-collected
    files/roles/manifests. Every finding cites a real path from `files` or
    `manifests`; confidence is "heuristic" throughout — nothing here is
    verified by static analysis, a secret scanner, or a vulnerability DB."""
    findings = []
    findings += _find_missing_test_coverage(files)
    findings += _find_secrets_risk(files)
    findings += _find_dependency_risk(manifests)
    return findings


def _find_missing_test_coverage(files: list[FileInfo]) -> list[Finding]:
    """Flag entrypoint files with no nearby test: none in the same directory,
    and no test_<name>/<name>_test/<name>.test.* file anywhere in the repo."""
    findings = []
    for f in files:
        if f.role == "entrypoint" and not _has_nearby_test(f, files):
            findings.append(Finding(
                severity="medium",
                category="missing-tests",
                title=f"No test coverage found near entrypoint `{f.path}`",
                evidence=[f.path],
                explanation=(
                    "This file is classified as an entrypoint, but no test file "
                    "was found in the same directory or matching its name "
                    "(test_<name>/<name>_test/<name>.test.*)."
                ),
                recommendation=f"Add a test covering `{f.path}`, alongside it or in a tests/ directory.",
                confidence="heuristic",
            ))
    return findings


def _has_nearby_test(entry: FileInfo, files: list[FileInfo]) -> bool:
    entry_path = Path(entry.path)
    test_files = [f for f in files if f.role == "test"]
    if any(Path(f.path).parent == entry_path.parent for f in test_files):
        return True
    stem = entry_path.stem
    name_patterns = {stem, f"test_{stem}", f"{stem}_test"}
    return any(Path(f.path).name.split(".")[0] in name_patterns for f in test_files)


def _find_secrets_risk(files: list[FileInfo]) -> list[Finding]:
    """Flag a committed `.env` with no `.env.example`/`.env.sample` template.
    Conservative by design: this does not read `.env`'s content or claim a
    secret was found, only that the pattern is present and worth confirming."""
    env_paths = [f.path for f in files if Path(f.path).name == ".env"]
    if not env_paths:
        return []
    names = {Path(f.path).name for f in files}
    if ".env.example" in names or ".env.sample" in names:
        return []
    return [Finding(
        severity="high",
        category="secrets-risk",
        title="`.env` file committed with no `.env.example` template",
        evidence=env_paths,
        explanation=(
            "A `.env` file is tracked in this repository and no `.env.example` "
            "or `.env.sample` was found. `.env` files commonly hold real secrets; "
            "if this one does, those secrets are now in git history."
        ),
        recommendation=(
            "Confirm whether `.env` holds real secrets. If so, remove it from git "
            "history and rotate any exposed credentials; add `.env` to `.gitignore` "
            "and commit a `.env.example` with placeholder values instead."
        ),
        confidence="heuristic",
    )]


def _find_dependency_risk(manifests: list[Manifest]) -> list[Finding]:
    findings = []
    for m in manifests:
        findings += _large_dependency_finding(m)
        findings += _unpinned_dependency_finding(m)
    return findings


def _large_dependency_finding(m: Manifest) -> list[Finding]:
    if len(m.dependencies) < LARGE_DEPENDENCY_THRESHOLD:
        return []
    return [Finding(
        severity="medium",
        category="dependency-risk",
        title=f"`{m.path}` lists {len(m.dependencies)} dependencies",
        evidence=[m.path],
        explanation=(
            f"This manifest declares {len(m.dependencies)} dependencies "
            f"(heuristic threshold: {LARGE_DEPENDENCY_THRESHOLD}), which increases "
            "supply-chain surface area and audit burden."
        ),
        recommendation="Review whether all dependencies are still in use; trim or audit unused ones.",
        confidence="heuristic",
    )]


def _unpinned_dependency_finding(m: Manifest) -> list[Finding]:
    if m.kind not in PIN_CHECKABLE_MANIFEST_KINDS or not m.dependencies:
        return []
    if any(_has_version_pin(dep) for dep in m.dependencies):
        return []
    return [Finding(
        severity="medium",
        category="dependency-risk",
        title=f"`{m.path}` pins no dependency versions",
        evidence=[m.path],
        explanation=(
            f"None of the {len(m.dependencies)} dependencies in this manifest specify "
            "a version constraint, which risks non-reproducible installs."
        ),
        recommendation="Pin dependency versions (e.g. `==`) or use a lockfile for reproducible builds.",
        confidence="heuristic",
    )]


def _has_version_pin(dependency: str) -> bool:
    return any(marker in dependency for marker in VERSION_PIN_MARKERS)


def group_into_modules(files: list[FileInfo], manifests: list[Manifest]) -> list[Module]:
    """Group files by top-level directory (files directly at the repo root
    form their own `ROOT_MODULE_NAME` group) and build one `Module` per
    group, already sorted into suggested read order (see `_module_sort_key`).
    A directory-based heuristic only — not an import/dependency analysis."""
    groups = _group_files_by_top_dir(files)
    manifest_paths = {m.path for m in manifests}
    modules = [_build_module(name, group, manifest_paths) for name, group in groups.items()]
    return sorted(modules, key=_module_sort_key)


def _group_files_by_top_dir(files: list[FileInfo]) -> dict[str, list[FileInfo]]:
    groups: dict[str, list[FileInfo]] = {}
    for f in files:
        parts = Path(f.path).parts
        name = parts[0] if len(parts) > 1 else ROOT_MODULE_NAME
        groups.setdefault(name, []).append(f)
    return groups


def _build_module(name: str, files: list[FileInfo], manifest_paths: set[str]) -> Module:
    key_files = _select_key_files(files)
    return Module(
        name=name,
        file_count=len(files),
        key_files=key_files,
        has_entrypoint=any(f.role == "entrypoint" for f in files),
        has_manifest=any(f.path in manifest_paths for f in files),
        description=_describe_module(name, files, key_files),
    )


def _select_key_files(files: list[FileInfo]) -> list[str]:
    """Entrypoints, then manifest/config files, then everything else (each
    tier alphabetical); capped so large directories stay readable."""
    def priority(f: FileInfo) -> tuple[int, str]:
        rank = 0 if f.role == "entrypoint" else 1 if f.role == "config" else 2
        return (rank, f.path)

    ranked = sorted(files, key=priority)
    return [f.path for f in ranked[:MAX_KEY_FILES_PER_MODULE]]


def _module_sort_key(module: Module) -> tuple[int, int, str]:
    """Suggested read order: modules with an entrypoint first, then modules
    with a manifest/config file, then everything else; ties within a tier
    broken by file count (most files first), then name alphabetically."""
    tier = 0 if module.has_entrypoint else 1 if module.has_manifest else 2
    return (tier, -module.file_count, module.name.lower())


def _describe_module(name: str, files: list[FileInfo], key_files: list[str]) -> str:
    """One paragraph: a fact sentence (file count/language/key file, all
    traceable to real paths) followed by an inference sentence (what the
    module is likely for, explicitly labeled as inferred from naming)."""
    return f"{_module_fact_sentence(name, files, key_files)} {_module_inference_sentence(name)}"


def _module_fact_sentence(name: str, files: list[FileInfo], key_files: list[str]) -> str:
    count = len(files)
    languages = {f.language for f in files}
    noun = f"{next(iter(languages))} file" if len(languages) == 1 else "file"
    noun += "s" if count != 1 else ""
    highlight = f", including `{key_files[0]}`" if key_files else ""
    if name == ROOT_MODULE_NAME:
        verb = "sits" if count == 1 else "sit"
        return f"{count} {noun} {verb} directly at the repo root{highlight}."
    return f"The `{name}/` directory holds {count} {noun}{highlight}."


def _module_inference_sentence(name: str) -> str:
    if name == ROOT_MODULE_NAME:
        return (
            "Root-level files are usually entrypoints, manifests, and docs rather "
            "than a single feature area (inferred from convention, not verified)."
        )
    purpose = INFERRED_MODULE_PURPOSE.get(name.lower())
    if purpose is None:
        return (
            f"No naming convention was recognized for `{name}/`, so its purpose "
            "isn't inferred here — see its key files below instead."
        )
    return f"Based on its directory name, this looks like the project's {purpose} (inferred from naming, not verified)."


# Node confidence: modules/manifests are real, already-parsed facts (a
# directory with N files exists; a manifest was parsed at this path) — not a
# guess. Edge confidence is "heuristic": edges come from regex text scanning
# (see below), not a real import resolver, so false negatives/positives are
# possible and must be labeled honestly rather than presented as certain.
NODE_CONFIDENCE = "structural"
EDGE_CONFIDENCE = "heuristic"
FLOW_CONFIDENCE = "heuristic"

_JS_LANGUAGES = {"JavaScript", "TypeScript"}
_PYTHON_MANIFEST_KINDS = {"python-pyproject", "python-requirements", "python-setuptools"}

# Regex-based import scanning only — no AST, no module resolver. Cheap and
# necessarily imperfect (e.g. a commented-out `import` line can still match);
# an edge is only ever emitted when the specifier resolves to a real module
# name or a real manifest dependency (see `_resolve_js_import`/
# `_resolve_python_import`), so false positives from the regex itself can
# only ever produce a dropped edge, never a fabricated one.
_JS_IMPORT_RE = re.compile(r"""import\s+(?:[^'"]*?\sfrom\s+)?['"]([^'"]+)['"]""")
_JS_REQUIRE_RE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
_PY_IMPORT_RE = re.compile(r"^\s*import\s+(.+)$", re.MULTILINE)
_PY_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([\w.]+)\s+import\s+", re.MULTILINE)


def build_graph(
    repo_path: Path, files: list[FileInfo], manifests: list[Manifest], modules: list[Module]
) -> tuple[list[Node], list[Edge]]:
    """The Slice 6 architecture graph: one `Node` per `Module` (type
    "module") and one `Node` per `Manifest` (type "dependency"), plus
    `Edge`s for import/dependency relationships detected by cheap regex
    scanning of JS/TS/Python source already present in `files`. Every edge's
    evidence is the real file path(s) the matching import text was found in;
    an import that can't be resolved to a known module or manifest dependency
    is dropped rather than guessed at."""
    nodes = _build_module_nodes(modules) + _build_manifest_nodes(manifests)
    edges = _detect_import_edges(repo_path, files, modules, manifests)
    return nodes, edges


def _build_module_nodes(modules: list[Module]) -> list[Node]:
    return [
        Node(
            id=f"module:{m.name}", label=m.name, type="module",
            file_paths=list(m.key_files), evidence=list(m.key_files),
            confidence=NODE_CONFIDENCE,
        )
        for m in modules
    ]


def _build_manifest_nodes(manifests: list[Manifest]) -> list[Node]:
    return [
        Node(
            id=f"manifest:{m.path}", label=m.name or m.path, type="dependency",
            file_paths=[m.path], evidence=[m.path], confidence=NODE_CONFIDENCE,
        )
        for m in manifests
    ]


def _detect_import_edges(
    repo_path: Path, files: list[FileInfo], modules: list[Module], manifests: list[Manifest]
) -> list[Edge]:
    module_names = {m.name for m in modules}
    manifests_by_language = _manifests_by_language(manifests)
    evidence_by_edge: dict[tuple[str, str, str], set[str]] = {}

    for f in files:
        source_module = _module_name_for_path(f.path)
        for specifier in _extract_import_specifiers(repo_path, f):
            target = _resolve_import_target(f, specifier, module_names, manifests_by_language)
            if target is None or target == ("module", source_module):
                continue
            kind, key = target
            edge_type = "imports" if kind == "module" else "depends_on"
            target_id = f"module:{key}" if kind == "module" else f"manifest:{key}"
            edge_key = (f"module:{source_module}", target_id, edge_type)
            evidence_by_edge.setdefault(edge_key, set()).add(f.path)

    return [
        Edge(
            source=source, target=target_id, type=edge_type,
            label="imports" if edge_type == "imports" else "depends on",
            evidence=sorted(evidence), confidence=EDGE_CONFIDENCE,
        )
        for (source, target_id, edge_type), evidence in sorted(evidence_by_edge.items())
    ]


def _module_name_for_path(path: str) -> str:
    parts = Path(path).parts
    return parts[0] if len(parts) > 1 else ROOT_MODULE_NAME


def _manifests_by_language(manifests: list[Manifest]) -> dict[str, list[Manifest]]:
    return {
        "npm": [m for m in manifests if m.kind == "npm"],
        "python": [m for m in manifests if m.kind in _PYTHON_MANIFEST_KINDS],
    }


def _extract_import_specifiers(repo_path: Path, f: FileInfo) -> list[str]:
    if f.language not in _JS_LANGUAGES and f.language != "Python":
        return []
    text = _read_text_safely(repo_path / f.path)
    if f.language == "Python":
        return _extract_python_imports(text)
    return _extract_js_imports(text)


def _read_text_safely(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def _extract_js_imports(text: str) -> list[str]:
    return [m.group(1) for m in _JS_IMPORT_RE.finditer(text)] + [
        m.group(1) for m in _JS_REQUIRE_RE.finditer(text)
    ]


def _extract_python_imports(text: str) -> list[str]:
    names = []
    for match in _PY_IMPORT_RE.finditer(text):
        body = match.group(1).split("#", 1)[0]
        for part in body.split(","):
            piece = part.strip().split(" as ")[0].strip()
            if piece:
                names.append(piece)
    for match in _PY_FROM_IMPORT_RE.finditer(text):
        names.append(match.group(1).strip())
    return names


def _resolve_import_target(
    f: FileInfo, specifier: str, module_names: set[str], manifests_by_language: dict[str, list[Manifest]],
) -> tuple[str, str] | None:
    if f.language in _JS_LANGUAGES:
        return _resolve_js_import(f.path, specifier, module_names, manifests_by_language["npm"])
    return _resolve_python_import(specifier, module_names, manifests_by_language["python"])


def _resolve_js_import(
    importer_path: str, specifier: str, module_names: set[str], npm_manifests: list[Manifest],
) -> tuple[str, str] | None:
    if specifier.startswith((".", "/")):
        target_module = _module_name_for_path(_resolve_relative_import(importer_path, specifier))
        return ("module", target_module) if target_module in module_names else None
    package_name = _js_package_name(specifier)
    for manifest in npm_manifests:
        if package_name in manifest.dependencies:
            return ("manifest", manifest.path)
    return None


def _js_package_name(specifier: str) -> str:
    parts = specifier.split("/")
    if specifier.startswith("@") and len(parts) > 1:
        return "/".join(parts[:2])
    return parts[0]


def _resolve_relative_import(importer_path: str, specifier: str) -> str:
    """Resolve a relative JS/TS import specifier against the importing
    file's directory into a repo-relative path string (no extension
    guessing — only the resulting top-level directory name is used, by
    `_module_name_for_path`)."""
    segments = list(Path(importer_path).parent.parts)
    for part in specifier.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if segments:
                segments.pop()
        else:
            segments.append(part)
    return "/".join(segments)


def _resolve_python_import(
    specifier: str, module_names: set[str], python_manifests: list[Manifest],
) -> tuple[str, str] | None:
    if specifier.startswith("."):
        return None  # relative import: assumed same-package, no cross-module edge inferred
    top_level = specifier.split(".")[0]
    if top_level in module_names:
        return ("module", top_level)
    for manifest in python_manifests:
        if top_level.lower() in _python_dependency_names(manifest):
            return ("manifest", manifest.path)
    return None


def _python_dependency_names(manifest: Manifest) -> set[str]:
    return {_strip_version_pin(dep).lower() for dep in manifest.dependencies}


def _strip_version_pin(dependency: str) -> str:
    for marker in VERSION_PIN_MARKERS:
        if marker in dependency:
            return dependency.split(marker)[0].strip()
    return dependency.strip()


def detect_flows(nodes: list[Node], edges: list[Edge], modules: list[Module]) -> list[Flow]:
    """The one flow type this slice detects: entrypoint reachability. For
    each module containing an entrypoint file, trace everything reachable
    from that module via the graph's already-computed edges (transitive
    closure) — reusing `build_graph`'s `nodes`/`edges` as-is, no new
    file-content parsing. An entrypoint with no outgoing edges still gets a
    flow (its explanation says so explicitly, per "no fake precision" — see
    `_describe_reachability_flow`); a flow is only skipped globally when
    there are no entrypoint modules at all, or the graph has no edges
    anywhere to trace (both would otherwise produce a fabricated-looking,
    edge-less "flow")."""
    entrypoint_modules = [m for m in modules if m.has_entrypoint]
    if not entrypoint_modules or not edges:
        return []
    nodes_by_id = {n.id: n for n in nodes}
    return [_build_reachability_flow(m, nodes_by_id, edges) for m in entrypoint_modules]


def _build_reachability_flow(module: Module, nodes_by_id: dict[str, Node], edges: list[Edge]) -> Flow:
    start_id = f"module:{module.name}"
    reached_ids, reached_edges = _trace_reachable_edges(start_id, edges)
    flow_nodes = [nodes_by_id[node_id] for node_id in reached_ids if node_id in nodes_by_id]
    evidence = sorted({path for node in flow_nodes for path in node.evidence})
    return Flow(
        title=f"Entrypoint reachability: {module.name}",
        nodes=flow_nodes,
        edges=reached_edges,
        explanation=_describe_reachability_flow(module, reached_edges),
        evidence=evidence,
        confidence=FLOW_CONFIDENCE,
    )


def _trace_reachable_edges(start_id: str, edges: list[Edge]) -> tuple[list[str], list[Edge]]:
    """Breadth-first reachability over the already-computed edge list,
    following only real `Edge`s whose `source` has been reached — a real
    subset of `RepoIndex.edges`, never invented."""
    visited_order = [start_id]
    seen = {start_id}
    queue = [start_id]
    reached_edges: list[Edge] = []
    while queue:
        current = queue.pop(0)
        for edge in edges:
            if edge.source != current:
                continue
            reached_edges.append(edge)
            if edge.target not in seen:
                seen.add(edge.target)
                visited_order.append(edge.target)
                queue.append(edge.target)
    return visited_order, reached_edges


def _describe_reachability_flow(module: Module, reached_edges: list[Edge]) -> str:
    """Plain-English explanation (PRD Flow Explorer requirement). An
    entrypoint with zero outgoing edges is explicitly called out as a
    missing/uncertain connection, never silently omitted or dressed up as
    a real flow with something to show."""
    entry_ref = "the repo root" if module.name == ROOT_MODULE_NAME else f"`{module.name}/`"
    if not reached_edges:
        return (
            f"Starting from the entrypoint in {entry_ref}, no outgoing imports or "
            "dependencies were detected to any other module or manifest. This is a "
            "missing/uncertain connection, not a claim that the entrypoint has no "
            "real dependencies — the regex-based import scanner may simply not "
            "have recognized its import style."
        )
    modules_reached = sorted({
        e.target.split(":", 1)[1] for e in reached_edges if e.type == "imports"
    })
    deps_reached = sorted({
        e.target.split(":", 1)[1] for e in reached_edges if e.type == "depends_on"
    })
    edge_count = len(reached_edges)
    sentence = (
        f"Starting from the entrypoint in {entry_ref}, this traces every module and "
        f"dependency reachable via {edge_count} detected import/dependency "
        f"edge{'s' if edge_count != 1 else ''}."
    )
    if modules_reached:
        sentence += f" Reaches module(s): {', '.join(modules_reached)}."
    if deps_reached:
        sentence += f" Depends on manifest(s): {', '.join(deps_reached)}."
    sentence += (
        " Edges come from regex-based import scanning (heuristic confidence), so "
        "this is a best-effort trace, not a verified call graph."
    )
    return sentence


@dataclass
class Subsystem:
    """A group of modules clustered by real import relationships (Slice 10
    of the understand-repo skill, docs/prd-understand-repo.md) — connected
    components over module->module "imports" edges only, no LLM involved.
    A module with no inter-module edges becomes its own singleton
    subsystem."""
    id: str
    name: str
    module_names: list[str]


def cluster_modules(nodes: list[Node], edges: list[Edge]) -> list[Subsystem]:
    """Groups module nodes into subsystems via connected components over
    "imports" edges only — "depends_on" edges (module->manifest) never merge
    modules together. Deterministic and reproducible: no LLM, no new
    file-content parsing, just a graph traversal over `build_graph`'s
    existing output."""
    module_names = [n.label for n in nodes if n.type == "module"]
    adjacency: dict[str, set[str]] = {name: set() for name in module_names}
    for e in edges:
        if e.type != "imports":
            continue
        source = e.source.removeprefix("module:")
        target = e.target.removeprefix("module:")
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)

    visited: set[str] = set()
    components: list[list[str]] = []
    for name in module_names:
        if name in visited:
            continue
        components.append(sorted(_connected_component(name, adjacency, visited)))

    components.sort(key=lambda names: (-len(names), names[0]))
    return [
        Subsystem(id=f"subsystem-{i}", name=" + ".join(names), module_names=names)
        for i, names in enumerate(components, start=1)
    ]


def _connected_component(start: str, adjacency: dict[str, set[str]], visited: set[str]) -> list[str]:
    stack = [start]
    visited.add(start)
    component = []
    while stack:
        current = stack.pop()
        component.append(current)
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                stack.append(neighbor)
    return component


def analyze_local_repo(repo_path: Path, url: str = "") -> RepoIndex:
    owner, name = (parse_github_url(url) if url else ("", repo_path.name))
    branch, commit_sha = "", ""
    if (repo_path / ".git").exists():
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        commit_sha = _git(repo_path, "rev-parse", "HEAD")

    files = scan_files(repo_path)
    language_counts: dict[str, int] = {}
    for f in files:
        language_counts[f.language] = language_counts.get(f.language, 0) + 1
    manifests = extract_manifests(repo_path, files)
    findings = generate_findings(files, manifests)
    modules = group_into_modules(files, manifests)
    nodes, edges = build_graph(repo_path, files, manifests, modules)
    flows = detect_flows(nodes, edges, modules)

    repo_info = RepoInfo(
        provider="github" if url else "local",
        owner=owner, name=name, branch=branch, commit_sha=commit_sha, url=url,
    )
    return RepoIndex(
        repo=repo_info, files=files, language_counts=language_counts,
        manifests=manifests, findings=findings, modules=modules,
        nodes=nodes, edges=edges, flows=flows,
    )


def analyze_github_repo(url: str) -> RepoIndex:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        clone_repo(url, dest)
        return analyze_local_repo(dest, url=url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a public GitHub repo into structured JSON")
    parser.add_argument("repo_url", help="Public GitHub repo URL, e.g. https://github.com/owner/name")
    args = parser.parse_args()
    index = analyze_github_repo(args.repo_url)
    print(json.dumps(asdict(index), indent=2))


if __name__ == "__main__":
    main()
