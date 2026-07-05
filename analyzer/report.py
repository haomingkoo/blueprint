"""Render a RepoIndex as a plain-English Markdown report (Slices 1-4)."""
from __future__ import annotations

from analyze import FileInfo, Finding, Manifest, Module, RepoIndex

# category -> section heading, in report display order.
FINDING_CATEGORIES = [
    ("missing-tests", "Missing Test Coverage"),
    ("secrets-risk", "Config & Secrets Risk"),
    ("dependency-risk", "Dependency Risk"),
]


def render_markdown(index: RepoIndex) -> str:
    repo = index.repo
    total_files = len(index.files)
    languages = sorted(index.language_counts.items(), key=lambda kv: -kv[1])
    top_language = languages[0][0] if languages else "unknown"

    lines = [
        f"# {repo.owner}/{repo.name}" if repo.owner else f"# {repo.name}",
        "",
        f"**Branch:** {repo.branch or 'n/a'} · "
        f"**Commit:** {repo.commit_sha[:7] if repo.commit_sha else 'n/a'} · "
        f"**URL:** {repo.url or 'local'}",
        "",
        f"This repo has {total_files} file{'s' if total_files != 1 else ''} "
        f"across {len(languages)} language{'s' if len(languages) != 1 else ''}, "
        f"dominated by {top_language}.",
        "",
        "## Files & Languages",
        "",
    ]
    for language, count in languages:
        lines.append(f"- {language}: {count} file{'s' if count != 1 else ''}")

    lines += ["", *_render_detected_stack(index.manifests)]
    lines += ["", *_render_entrypoints(index.files)]
    lines += ["", *_render_review_findings(index.findings)]
    lines += ["", *_render_start_here(index.modules)]

    return "\n".join(lines) + "\n"


def _render_detected_stack(manifests: list[Manifest]) -> list[str]:
    lines = ["## Detected Stack", ""]
    if not manifests:
        lines.append("No manifest files detected.")
        return lines
    for manifest in manifests:
        lines += _render_manifest(manifest)
    return lines


def _render_manifest(manifest: Manifest) -> list[str]:
    label = f"`{manifest.path}` ({manifest.kind})"
    if manifest.name:
        label += f" — {manifest.name}"
    lines = [f"### {label}", ""]
    if manifest.dependencies:
        shown = ", ".join(manifest.dependencies[:10])
        remainder = len(manifest.dependencies) - 10
        if remainder > 0:
            shown += f", +{remainder} more"
        lines.append(f"- Dependencies: {shown}")
    if manifest.scripts:
        scripts = ", ".join(f"`{name}`" for name in manifest.scripts)
        lines.append(f"- Scripts: {scripts}")
    if not manifest.dependencies and not manifest.scripts:
        lines.append("- No dependencies or scripts extracted.")
    lines.append("")
    return lines


def _render_entrypoints(files: list[FileInfo]) -> list[str]:
    lines = ["## Entrypoints", ""]
    entrypoints = [f for f in files if f.role == "entrypoint"]
    if not entrypoints:
        lines.append("No entrypoints detected.")
        return lines
    for f in entrypoints:
        lines.append(f"- `{f.path}`")
    return lines


def _render_review_findings(findings: list[Finding]) -> list[str]:
    lines = ["## Review Findings", ""]
    for category, heading in FINDING_CATEGORIES:
        matching = [f for f in findings if f.category == category]
        lines += _render_finding_category(heading, matching)
    return lines


def _render_finding_category(heading: str, findings: list[Finding]) -> list[str]:
    lines = [f"### {heading}", ""]
    if not findings:
        lines += ["No findings in this category.", ""]
        return lines
    for f in findings:
        lines += _render_finding(f)
    return lines


def _render_finding(f: Finding) -> list[str]:
    evidence = ", ".join(f"`{path}`" for path in f.evidence)
    return [
        f"- **[{f.severity}] {f.title}** (confidence: {f.confidence})",
        f"  - Evidence: {evidence}",
        f"  - Why it matters: {f.explanation}",
        f"  - Recommendation: {f.recommendation}",
        "",
    ]


def _render_start_here(modules: list[Module]) -> list[str]:
    lines = ["## Start Here", ""]
    if not modules:
        lines.append("No modules detected.")
        return lines
    lines += [
        "Modules below are ordered by suggested read order: modules with an "
        "entrypoint first, then modules with a manifest/config file, then "
        "everything else.",
        "",
    ]
    for module in modules:
        lines += _render_module(module)
    return lines


def _render_module(module: Module) -> list[str]:
    lines = [f"### {module.name}", "", module.description, ""]
    if module.key_files:
        key_files = ", ".join(f"`{path}`" for path in module.key_files)
        lines.append(f"Key files: {key_files}")
    lines.append("")
    return lines
