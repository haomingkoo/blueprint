"""Render a RepoIndex as a plain-English Markdown report (Slice 1 + Slice 2)."""
from __future__ import annotations

from analyze import FileInfo, Manifest, RepoIndex


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
