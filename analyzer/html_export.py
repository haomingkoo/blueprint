"""Self-contained HTML export (Slice 8): the same report content
`report.py`'s `render_markdown` covers (Overview, Detected Stack,
Entrypoints, Review Findings, Start Here), packaged as one standalone HTML
document -- inline CSS, a system font stack (no bundled/linked font
files), no external `<link>`/`<script src>` references, safe to open via
`file://` with zero network access. Mirrors report.py's per-section
structure (the same duplication-is-fine tradeoff Slice 5 already made
between report.py's Markdown and app.js's HTML rendering, per
docs/HANDOFF.md) rather than converting render_markdown()'s text output --
our own Markdown includes a nested list per finding that a from-scratch
Markdown-to-HTML converter would have to special-case anyway.

Every value that ultimately comes from the analyzed repo's own file
content/paths/names (untrusted -- Blueprint can be pointed at any public
repo) is HTML-escaped before being embedded, per security.md's "escape
HTML output to prevent XSS" and the same convention app.js already follows
(never uses innerHTML with repo-derived text).
"""
from __future__ import annotations

from html import escape as _esc

from analyze import FileInfo, Finding, Manifest, Module, RepoIndex, RepoInfo

FINDING_CATEGORIES = [
    ("missing-tests", "Missing Test Coverage"),
    ("secrets-risk", "Config & Secrets Risk"),
    ("dependency-risk", "Dependency Risk"),
]

# System font stack only -- no @font-face/url()/CDN link, so this document
# has zero network dependency when opened via file://.
_CSS = """
:root { color-scheme: dark; }
body {
  margin: 0; padding: 2.5rem 1.5rem 4rem; max-width: 860px; margin-inline: auto;
  background: #060b16; color: #eef4ff;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
}
h1, h2, h3 {
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
  color: #eef4ff;
}
h1 { font-size: 1.8rem; margin: 0 0 0.5rem; }
h2 { font-size: 1.2rem; margin: 2rem 0 0.75rem; border-top: 1px dashed #24406b; padding-top: 1.5rem; }
h2:first-of-type { border-top: none; padding-top: 0; }
h3 { font-size: 1rem; margin: 1.25rem 0 0.5rem; color: #9fe8ff; }
.meta { font-family: ui-monospace, monospace; color: #9fb3d1; font-size: 0.9rem; }
code {
  background: #0e2038; border: 1px solid #24406b; border-radius: 3px;
  padding: 0.1rem 0.4rem; font-size: 0.86rem; color: #9fe8ff;
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
}
ul { padding-left: 1.4rem; }
.card { border: 1px solid #24406b; border-radius: 3px; padding: 1rem 1.1rem; margin-bottom: 0.9rem; background: #0e2038; }
.finding { border-left: 3px solid #8fa3c7; }
.finding[data-severity="critical"] { border-left-color: #ff5d7a; }
.finding[data-severity="high"] { border-left-color: #ff8a5b; }
.finding[data-severity="medium"] { border-left-color: #ffc266; }
.finding[data-severity="low"] { border-left-color: #6fd7a3; }
.badge {
  font-family: ui-monospace, monospace; font-size: 0.75rem; text-transform: uppercase;
  letter-spacing: 0.04em; color: #7d93bd; border: 1px solid #24406b; border-radius: 999px;
  padding: 0.1rem 0.55rem; margin-left: 0.5rem;
}
.empty { font-style: italic; color: #5d7396; }
footer { margin-top: 3rem; font-size: 0.8rem; color: #5d7396; font-family: ui-monospace, monospace; }
"""


def render_html_report(index: RepoIndex) -> str:
    """A single self-contained HTML document covering the same sections as
    `report.py`'s Markdown report: repo URL/commit SHA visible in the
    page, styles inlined, system font stack, no external `<link>`/
    `<script src>` references -- safe to open via `file://` with zero
    network access."""
    repo = index.repo
    title = _esc(_repo_label(repo))
    body = "\n".join([
        _render_header(repo),
        _render_overview(index),
        _render_detected_stack(index.manifests),
        _render_entrypoints(index.files),
        _render_review_findings(index.findings),
        _render_start_here(index.modules),
        _render_footer(),
    ])
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{title} — Blueprint report</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def _repo_label(repo: RepoInfo) -> str:
    return f"{repo.owner}/{repo.name}" if repo.owner else repo.name


def _render_header(repo: RepoInfo) -> str:
    label = _esc(_repo_label(repo))
    commit = _esc(repo.commit_sha[:7]) if repo.commit_sha else "n/a"
    branch = _esc(repo.branch) if repo.branch else "n/a"
    url = _esc(repo.url) if repo.url else "local"
    return (
        f"<h1>{label}</h1>\n"
        f'<p class="meta">Branch: {branch} &middot; Commit: {commit} &middot; URL: {url}</p>'
    )


def _render_overview(index: RepoIndex) -> str:
    total_files = len(index.files)
    languages = sorted(index.language_counts.items(), key=lambda kv: -kv[1])
    top_language = languages[0][0] if languages else "unknown"
    summary = (
        f"This repo has {total_files} file{'s' if total_files != 1 else ''} "
        f"across {len(languages)} language{'s' if len(languages) != 1 else ''}, "
        f"dominated by {_esc(top_language)}."
    )
    items = "".join(
        f"<li>{_esc(lang)}: {count} file{'s' if count != 1 else ''}</li>"
        for lang, count in languages
    )
    return f"<h2>Files &amp; Languages</h2>\n<p>{summary}</p>\n<ul>{items}</ul>"


def _render_detected_stack(manifests: list[Manifest]) -> str:
    if not manifests:
        return '<h2>Detected Stack</h2>\n<p class="empty">No manifest files detected.</p>'
    cards = "".join(_render_manifest(m) for m in manifests)
    return f"<h2>Detected Stack</h2>\n{cards}"


def _render_manifest(manifest: Manifest) -> str:
    label = f"<code>{_esc(manifest.path)}</code> ({_esc(manifest.kind)})"
    if manifest.name:
        label += f" — {_esc(manifest.name)}"
    rows = []
    if manifest.dependencies:
        shown = ", ".join(_esc(d) for d in manifest.dependencies[:10])
        remainder = len(manifest.dependencies) - 10
        if remainder > 0:
            shown += f", +{remainder} more"
        rows.append(f"<p>Dependencies: {shown}</p>")
    if manifest.scripts:
        scripts = ", ".join(f"<code>{_esc(name)}</code>" for name in manifest.scripts)
        rows.append(f"<p>Scripts: {scripts}</p>")
    if not manifest.dependencies and not manifest.scripts:
        rows.append("<p>No dependencies or scripts extracted.</p>")
    return f'<div class="card"><h3>{label}</h3>{"".join(rows)}</div>'


def _render_entrypoints(files: list[FileInfo]) -> str:
    entrypoints = [f for f in files if f.role == "entrypoint"]
    if not entrypoints:
        return '<h2>Entrypoints</h2>\n<p class="empty">No entrypoints detected.</p>'
    items = "".join(f"<li><code>{_esc(f.path)}</code></li>" for f in entrypoints)
    return f"<h2>Entrypoints</h2>\n<ul>{items}</ul>"


def _render_review_findings(findings: list[Finding]) -> str:
    sections = "".join(
        _render_finding_category(heading, [f for f in findings if f.category == category])
        for category, heading in FINDING_CATEGORIES
    )
    return f"<h2>Review Findings</h2>\n{sections}"


def _render_finding_category(heading: str, findings: list[Finding]) -> str:
    if not findings:
        return f'<h3>{_esc(heading)}</h3>\n<p class="empty">No findings in this category.</p>'
    cards = "".join(_render_finding(f) for f in findings)
    return f"<h3>{_esc(heading)}</h3>\n{cards}"


def _render_finding(f: Finding) -> str:
    evidence = ", ".join(f"<code>{_esc(path)}</code>" for path in f.evidence)
    return (
        f'<div class="card finding" data-severity="{_esc(f.severity)}">'
        f"<p><strong>{_esc(f.title)}</strong> "
        f'<span class="badge">{_esc(f.severity)}</span> '
        f'<span class="badge">confidence: {_esc(f.confidence)}</span></p>'
        f"<p>Evidence: {evidence}</p>"
        f"<p>Why it matters: {_esc(f.explanation)}</p>"
        f"<p>Recommendation: {_esc(f.recommendation)}</p>"
        "</div>"
    )


def _render_start_here(modules: list[Module]) -> str:
    if not modules:
        return '<h2>Start Here</h2>\n<p class="empty">No modules detected.</p>'
    cards = "".join(_render_module(m) for m in modules)
    return f"<h2>Start Here</h2>\n{cards}"


def _render_module(module: Module) -> str:
    key_files = ""
    if module.key_files:
        chips = ", ".join(f"<code>{_esc(path)}</code>" for path in module.key_files)
        key_files = f"<p>Key files: {chips}</p>"
    return (
        f'<div class="card"><h3>{_esc(module.name)}</h3>'
        f"<p>{_esc(module.description)}</p>{key_files}</div>"
    )


def _render_footer() -> str:
    return "<footer>Generated by Blueprint · standalone offline export</footer>"
