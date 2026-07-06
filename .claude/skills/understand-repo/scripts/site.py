#!/usr/bin/env python3
"""understand-repo Slice 13: multi-page HTML site.

Same sweep data as report.md (Slices 11-12), a different surface -- a
browsable, linkable site instead of one Markdown file. The index page
carries a clickable Mermaid diagram of the subsystem graph (one box per
subsystem, real depends_on edges to manifests) rendered client-side by a
vendored mermaid.js -- no CDN, no network access needed to view it, and
clicking a subsystem box opens its own page via Mermaid's `click` directive.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
from pathlib import Path

from edges import load_edges_with_descriptions

_E = html.escape
VENDOR_DIR = Path(__file__).resolve().parent / "vendor"

# Same dark "blueprint" palette as analyzer/html_export.py's existing
# standalone report export -- reused, not reinvented, per the PRD.
_CSS = """
:root { color-scheme: dark; }
body {
  margin: 0; padding: 2.5rem 1.5rem 4rem; max-width: 900px; margin-inline: auto;
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
.card { border: 1px solid #24406b; border-radius: 3px; padding: 1rem 1.1rem; margin-bottom: 0.9rem; background: #0e2038; }
.badge {
  font-family: ui-monospace, monospace; font-size: 0.75rem; text-transform: uppercase;
  letter-spacing: 0.04em; color: #7d93bd; border: 1px solid #24406b; border-radius: 999px;
  padding: 0.1rem 0.55rem; margin-left: 0.5rem;
}
.badge.verified { color: #6fd7a3; border-color: #2f6b4d; }
.empty { font-style: italic; color: #5d7396; }
.back { font-family: ui-monospace, monospace; font-size: 0.85rem; color: #9fe8ff; text-decoration: none; }
.mermaid-wrap { background: #0e2038; border: 1px solid #24406b; border-radius: 3px; padding: 1rem; overflow-x: auto; }
table.files { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
table.files th { text-align: left; color: #7d93bd; font-family: ui-monospace, monospace; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; padding: 0.4rem 0.6rem; border-bottom: 1px solid #24406b; }
table.files td { padding: 0.4rem 0.6rem; border-bottom: 1px solid #182c47; }
footer { margin-top: 3rem; font-size: 0.8rem; color: #5d7396; font-family: ui-monospace, monospace; }
"""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "root"


def load_sweep_data(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        repo_name, overview = conn.execute("SELECT repo_name, overview FROM sweeps LIMIT 1").fetchone()
        subsystem_rows = conn.execute("SELECT id, name, narrative FROM subsystems ORDER BY name").fetchall()
        module_subsystem_rows = conn.execute("SELECT subsystem_id, module_name FROM module_subsystem").fetchall()
        module_rows = conn.execute("SELECT module_name, key_files FROM modules").fetchall()
        summary_rows = conn.execute(
            "SELECT module_name, summary_text, evidence_files FROM semantic_summaries"
        ).fetchall()
        file_rows = conn.execute("SELECT module_name, path, role, language FROM module_files").fetchall()
    finally:
        conn.close()
    # Own connection (see load_edges_with_descriptions) -- joins in any
    # verified Phase 4 description so a described edge shows its sentence
    # instead of the plain structural label.
    edges = load_edges_with_descriptions(db_path)

    modules_by_subsystem: dict[str, list[str]] = {}
    for subsystem_id, module_name in module_subsystem_rows:
        modules_by_subsystem.setdefault(subsystem_id, []).append(module_name)

    files_by_module: dict[str, list[dict]] = {}
    for module_name, path, role, language in file_rows:
        files_by_module.setdefault(module_name, []).append(
            {"path": path, "role": role, "language": language}
        )

    return {
        "repo_name": repo_name,
        "overview": overview,
        "subsystems": [
            {
                "id": sid, "name": name, "narrative": narrative,
                "modules": sorted(modules_by_subsystem.get(sid, [])),
            }
            for sid, name, narrative in subsystem_rows
        ],
        "subsystem_by_module": {m: s for s, m in module_subsystem_rows},
        "key_files_by_module": {name: json.loads(kf) for name, kf in module_rows},
        "summary_by_module": {name: (text, json.loads(ev)) for name, text, ev in summary_rows},
        "edges": edges,
        "files_by_module": files_by_module,
    }


def _subsystem_is_verified(subsystem: dict, data: dict) -> bool:
    return any(m in data["summary_by_module"] for m in subsystem["modules"])


def render_mermaid_source(data: dict) -> str:
    """One node per subsystem (never per module -- that's the whole point
    of clustering) plus one node per manifest a subsystem really depends on,
    joined by real depends_on edges only. `imports` edges are never
    inter-subsystem by construction (cluster_modules already merged any
    module pair connected by one), so they're skipped here rather than
    drawn as a same-box self-loop."""
    lines = ["graph LR"]
    safe_id = {s["id"]: f"s{i}" for i, s in enumerate(data["subsystems"])}
    manifest_ids: dict[str, str] = {}

    for s in data["subsystems"]:
        sid = safe_id[s["id"]]
        label = s["name"] if len(s["modules"]) <= 1 else f'{s["name"]} ({len(s["modules"])} modules)'
        lines.append(f'    {sid}["{_mermaid_label(label)}"]')
        lines.append(f'    click {sid} "{_slugify(s["name"])}.html" "Open {_mermaid_label(s["name"])}"')
        status = "verified" if _subsystem_is_verified(s, data) else "neutral"
        lines.append(f"    class {sid} {status}")

    for edge in data["edges"]:
        if edge["type"] != "depends_on" or not edge["target"].startswith("manifest:"):
            continue
        source_module = edge["source"].removeprefix("module:")
        subsystem_id = data["subsystem_by_module"].get(source_module)
        if subsystem_id not in safe_id:
            continue
        manifest_name = edge["target"].removeprefix("manifest:")
        if edge["target"] not in manifest_ids:
            manifest_ids[edge["target"]] = f"m{len(manifest_ids)}"
            lines.append(f'    {manifest_ids[edge["target"]]}(("{_mermaid_label(manifest_name)}"))')
        lines.append(f'    {safe_id[subsystem_id]} -.->|depends on| {manifest_ids[edge["target"]]}')

    lines.append("    classDef verified fill:#123a2a,stroke:#6fd7a3,color:#eef4ff;")
    lines.append("    classDef neutral fill:#0e2038,stroke:#24406b,color:#9fb3d1;")
    return "\n".join(lines)


def _mermaid_label(text: str) -> str:
    return text.replace('"', "'")


def render_index(data: dict) -> str:
    repo_name = _E(data["repo_name"])
    overview = _E(data["overview"]) if data["overview"] else '<span class="empty">No synthesis overview yet.</span>'
    mermaid_source = render_mermaid_source(data)

    subsystem_cards = []
    for s in data["subsystems"]:
        verified = _subsystem_is_verified(s, data)
        badge = '<span class="badge verified">verified</span>' if verified else ""
        narrative = s["narrative"] or "No synthesized narrative yet."
        one_line = narrative if len(narrative) <= 160 else narrative[:157] + "..."
        href = f"{_slugify(s['name'])}.html"
        subsystem_cards.append(
            f'<div class="card"><h3><a class="back" href="{_E(href)}">{_E(s["name"])}</a>{badge}</h3>'
            f'<p>{_E(one_line)}</p>'
            f'<p class="meta">{len(s["modules"])} module{"s" if len(s["modules"]) != 1 else ""}</p></div>'
        )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{repo_name} — Understanding Site</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        f"<h1>{repo_name}</h1>\n"
        f'<p class="meta">Understand-repo sweep — subsystem overview</p>\n'
        f"<h2>Overview</h2>\n<p>{overview}</p>\n"
        "<h2>Subsystem Graph</h2>\n"
        f'<div class="mermaid-wrap"><pre class="mermaid">{_E(mermaid_source)}</pre></div>\n'
        "<h2>Subsystems</h2>\n"
        f"{''.join(subsystem_cards)}\n"
        '<script src="vendor/mermaid.min.js"></script>\n'
        "<script>mermaid.initialize({ startOnLoad: true, theme: 'dark' });</script>\n"
        "<footer>Generated by understand-repo · standalone offline site</footer>\n"
        "</body>\n</html>\n"
    )


def render_subsystem_page(subsystem: dict, data: dict) -> str:
    name = _E(subsystem["name"])
    narrative = _E(subsystem["narrative"]) if subsystem["narrative"] else '<span class="empty">No synthesized narrative yet for this subsystem.</span>'

    module_cards = []
    for module_name in subsystem["modules"]:
        key_files = data["key_files_by_module"].get(module_name, [])
        files_html = ", ".join(f"<code>{_E(f)}</code>" for f in key_files) or '<span class="empty">no files recorded</span>'
        if module_name in data["summary_by_module"]:
            summary_text, evidence_files = data["summary_by_module"][module_name]
            evidence_html = ", ".join(f"<code>{_E(f)}</code>" for f in evidence_files)
            module_cards.append(
                f'<div class="card"><h3>{_E(module_name)}<span class="badge verified">verified</span></h3>'
                f"<p>{_E(summary_text)}</p>"
                f"<p>Evidence: {evidence_html}</p></div>"
            )
        else:
            module_cards.append(
                f'<div class="card"><h3>{_E(module_name)}</h3>'
                '<p class="empty">No verified semantic summary this sweep.</p>'
                f"<p>Key files: {files_html}</p></div>"
            )

    edge_items = _render_subsystem_edges(subsystem, data)
    files_html = _render_subsystem_files(subsystem, data)

    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{name} — {_E(data['repo_name'])}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n"
        '<a class="back" href="index.html">&larr; back to overview</a>\n'
        f"<h1>{name}</h1>\n"
        f"<p>{narrative}</p>\n"
        "<h2>Modules</h2>\n"
        f"{''.join(module_cards)}\n"
        "<h2>Files</h2>\n"
        f"{files_html}\n"
        "<h2>Edges</h2>\n"
        f"{edge_items}\n"
        "<footer>Generated by understand-repo · standalone offline site</footer>\n"
        "</body>\n</html>\n"
    )


def _render_subsystem_files(subsystem: dict, data: dict) -> str:
    """A plain, honest orientation list -- every real file in this
    subsystem with its structural role and language, nothing invented.
    No file-to-file edges are drawn: the analyzer only ever tracks
    imports at module granularity (same-module imports are dropped, see
    analyze.py's build_graph), so a file-to-file connection here would be
    a guess, not a fact."""
    rows = []
    for module_name in subsystem["modules"]:
        for f in sorted(data["files_by_module"].get(module_name, []), key=lambda f: f["path"]):
            rows.append(
                "<tr>"
                f"<td><code>{_E(f['path'])}</code></td>"
                f'<td><span class="badge">{_E(f["role"])}</span></td>'
                f"<td>{_E(f['language'])}</td>"
                "</tr>"
            )
    if not rows:
        return '<p class="empty">No files recorded for this subsystem.</p>'
    return (
        '<div style="overflow-x:auto"><table class="files">'
        "<thead><tr><th>Path</th><th>Role</th><th>Language</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _render_subsystem_edges(subsystem: dict, data: dict) -> str:
    module_names = set(subsystem["modules"])
    items = []
    for edge in data["edges"]:
        source_module = edge["source"].removeprefix("module:")
        if source_module not in module_names:
            continue
        target = edge["target"].removeprefix("manifest:").removeprefix("module:")
        if "description" in edge:
            items.append(
                f"<li><code>{_E(source_module)}</code> &rarr; <code>{_E(target)}</code>: "
                f"{_E(edge['description'])}</li>"
            )
        else:
            items.append(f"<li><code>{_E(source_module)}</code> {_E(edge['label'])} <code>{_E(target)}</code></li>")
    if not items:
        return '<p class="empty">No real edges detected within or leaving this subsystem.</p>'
    return f"<ul>{''.join(items)}</ul>"


def build_site(sweep_dir: Path) -> Path:
    data = load_sweep_data(sweep_dir / "understanding.db")
    site_dir = sweep_dir / "site"
    site_dir.mkdir(exist_ok=True)

    (site_dir / "index.html").write_text(render_index(data))
    for s in data["subsystems"]:
        (site_dir / f"{_slugify(s['name'])}.html").write_text(render_subsystem_page(s, data))

    site_vendor = site_dir / "vendor"
    site_vendor.mkdir(exist_ok=True)
    shutil.copyfile(VENDOR_DIR / "mermaid.min.js", site_vendor / "mermaid.min.js")
    shutil.copyfile(VENDOR_DIR / "mermaid-LICENSE", site_vendor / "mermaid-LICENSE")

    return site_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the multi-page HTML site for a sweep")
    parser.add_argument("sweep_dir")
    args = parser.parse_args()
    site_dir = build_site(Path(args.sweep_dir))
    print(f"Site written to {site_dir}")


if __name__ == "__main__":
    main()
