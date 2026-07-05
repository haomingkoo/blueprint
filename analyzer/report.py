"""Render a RepoIndex as a plain-English Markdown report (Slice 1)."""
from __future__ import annotations

from analyze import RepoIndex


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

    return "\n".join(lines) + "\n"
