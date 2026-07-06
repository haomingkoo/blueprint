# Backlog: Vertical Slices

Tracer-bullet approach: each slice is a narrow but complete path from repo URL
to a user-visible output (analyzer -> synthesis -> UI), demoable on its own.
No slice waits for a full layer (e.g. "the whole graph engine") to finish first —
width gets added slice by slice. The core objective is codebase review + onboarding
descriptions; the interactive graph is a later slice, not the foundation.

Output starts as CLI/Markdown (cheap, fast to verify) and only becomes a web UI
once the analysis itself is proven — a slick frontend on weak analysis is the
core risk (see `grill-me.md` #15).

## Slice 1: Repo -> Plain-English Summary (CLI)

Paste a GitHub URL, get back a readable summary: repo name, branch, commit SHA,
file count, language breakdown.

Status: analyzer core (`analyzer/analyze.py`) already does clone + file scan +
language counts. What's missing is the synthesis + CLI layer.

Acceptance criteria:

- `analyzer/cli.py <repo-url>` prints a Markdown report to stdout.
- Report includes repo metadata, file/language counts, one summary sentence.
- Works end-to-end against a real public repo, not just fixture JSON.
- One runnable check (fixture repo, no network).

Skipped for now: dependency detection, review findings, web UI.

## Slice 2: Add Manifests, Entrypoints, Tests to the Summary

Same CLI path, richer report — now the summary can name the framework and
where to start reading.

Acceptance criteria:

- Detects common manifests: `package.json`, `pyproject.toml`, `requirements.txt`, `setup.py`.
- Extracts package scripts/dependencies where straightforward.
- Marks likely entrypoints, test files, config files, docs files, with evidence path.
- CLI report gains a "Detected Stack" and "Entrypoints" section.
- One runnable check with a tiny fixture repo.

Skipped for now: every ecosystem/lockfile nuance.

## Slice 3: Add Review Findings to the Report

Same CLI path — now the report includes an evidence-backed critique, not just
description.

Acceptance criteria:

- Emits findings with severity, category, title, evidence, explanation,
  recommendation, confidence.
- Covers at least: missing tests around key files, config/secrets risk,
  dependency risk.
- CLI report gains a "Review Findings" section.
- Findings never claim certainty without evidence.
- One runnable check per finding category against a fixture repo.

Skipped for now: auto-fix, full architecture-clarity scoring.

## Slice 4: Add Per-Module Descriptions ("Start Here" Guide)

Same CLI path — now a new joiner can read the report and know where to look
first. This is the other half of the core objective.

Acceptance criteria:

- Groups files into modules/components (directory-based heuristic is enough).
- One paragraph per module: what it is, why it likely exists, key files.
- CLI report gains a "Key Files & Modules" / "Start Here" section, ordered by
  suggested read order (entrypoints first).
- Inference-based claims are labeled as inference, not fact.
- One runnable check against a fixture repo with 2+ modules.

Skipped for now: symbol-level walkthroughs, LLM-authored prose (heuristic
templates are enough until Slice 1-3 prove out).

## Slice 5: Wrap the Report in a Minimal Web UI

Same analysis, new surface: paste the URL in a browser instead of a terminal.

Acceptance criteria:

- Local server (FastAPI) with one endpoint: POST repo URL -> JSON report.
- One page: URL input, Analyze button, loading state, rendered report
  (Overview / Detected Stack / Start Here / Review Findings as sections).
- No graph yet — this slice is the CLI output, rendered in HTML.
- Works against a real public repo end-to-end in the browser.

Skipped for now: auth, hosting/deploy, history, graph.

## Slice 6: Add the Architecture Graph

Same web UI — now the report includes the archmap-style interactive graph as
an additional view, not a replacement for the text report.

Acceptance criteria:

- Emits `Node[]`/`Edge[]` from the index (modules, external deps, config,
  tests, docs; import/dependency edges where detectable).
- Each node/edge carries evidence and confidence.
- Graph view: pan, zoom, fit, search, filter chips by node type with counts.
- Click a node -> drawer with type, label, technology, files, confidence.
- Mermaid export works from the same graph JSON.
- Layout uses automatic collision avoidance (e.g. dagre/elkjs) — no overlapping
  nodes, edges, or edge labels at any zoom level. This is a QA gate, not a
  nice-to-have: screenshot the rendered graph for 2-3 sample repos as part of
  verifying this slice.

Skipped for now: function-level graphs, perfect semantic call graph.

## Slice 7: Add One Flow Explorer

Same web UI — now one important flow (e.g. JS/TS route-to-handler, or Python
API-to-internal-module) can be viewed on its own instead of the full graph.

Acceptance criteria:

- Detects one flow type for one supported stack.
- Emits flow title, ordered nodes/edges, explanation, evidence, confidence.
- UI shows the flow separately from the full graph.
- Missing links are marked uncertain instead of invented.

Skipped for now: all frameworks, multiple flow types.

## Slice 8: Export

Make the same outputs usable outside the app.

Acceptance criteria:

- Copy Mermaid for the current graph or selected flow.
- Copy Markdown for overview, start-here guide, and review report.
- Download a single self-contained HTML file of the full rendered report
  (styles inlined, no external requests) — so it can be sent to someone or
  opened offline without running the app.
- Export includes repo URL and commit SHA.

Skipped for now: PDF, advanced PNG styling.

## Slice 9: Analysis History

Keep recent analyses locally so re-opening doesn't re-clone.

Acceptance criteria:

- Shows recent analyses: repo name, commit SHA/date, node count, finding count.
- Reopens a previous analysis without re-cloning if JSON exists locally.
- Can delete a history item.

Skipped for now: cloud accounts, team history.

---

The following slices belong to a separate tool (`docs/prd-understand-repo.md`)
that ships in this repo and depends on the analyzer above, but isn't part of
the web app's Slice 1-9 numbering in spirit — it's a Claude Code skill, not a
web UI feature. Numbering continues from 9 anyway since this is the same
backlog file and build-order convention (prove the analysis before building
a visual layer) still applies.

## Slice 10: Cluster Modules Into Subsystems (No LLM Yet)

Same analyzer core, new command — reuses `analyze_local_repo`'s existing
`Node`/`Edge` graph and groups module-nodes into subsystems by connected
components over `"imports"` edges. No semantic layer yet; this slice proves
the deterministic backbone the rest of the skill sits on.

Acceptance criteria:

- New clustering function: `cluster_modules(nodes, edges) -> list[Subsystem]`,
  connected components over module→module `"imports"` edges only.
- A module with no inter-module edges becomes its own singleton subsystem —
  no crash, no special-casing.
- New `/understand-repo <path>` skill scaffold (built with skill-creator)
  that: runs the structural pass, runs clustering, writes a `sweeps` SQLite
  row + `subsystems`/`module_subsystem` rows under
  `blueprint/.understanding/<repo-name>/<timestamp>-<sha>/understanding.db`,
  and prints a plain-text list of subsystems + their modules to the terminal.
- Re-running on the same repo creates a new timestamped sweep directory
  rather than overwriting the last one; a `latest` pointer is updated.
- One runnable check: a fixture repo with a known edge shape asserting
  correct cluster membership + the singleton case.

Skipped for now: semantic summaries, HTML site, Markdown report — this
slice is structure + persistence only.

## Slice 11: Verified Per-Module Semantic Summaries

Same skill, richer output — now each module gets an AI-written summary, but
only after a second independent agent fails to refute it.

Acceptance criteria:

- Ultracode pipeline, one stage per module: Agent A writes a summary citing
  specific evidence files; Agent B independently re-reads the same files
  and attempts to refute Agent A's claim.
- Only claims Agent B can't refute are kept, written to a new
  `semantic_summaries` table tagged `confidence="semantic"` — a new tier
  alongside the existing `"structural"`/`"heuristic"`.
- A module where every claim is refuted still appears in the sweep
  (structural facts only) with an explicit "no verified semantic summary
  this sweep" note — never silently dropped.
- An agent call that fails outright falls back to the same
  "structural only" path; the sweep continues for remaining modules.
- Markdown report (`report.md` in the sweep directory) gains a per-module
  "AI Interpretation — verified" section listing only kept claims and their
  evidence.
- One runnable check against the DB writer/report renderer (fixture
  summaries in, correct rows/Markdown out) — the LLM stages themselves are
  verified by one real manual sweep, hand-reviewed for hallucination.

Skipped for now: subsystem-level narrative, HTML site.

## Slice 12: Subsystem Synthesis Narrative

Same skill — now the per-module facts add up to a story: what each
subsystem is for, and how subsystems connect.

Acceptance criteria:

- One synthesis agent, given only the verified per-module summaries
  (Slice 11) + cluster assignments (Slice 10) + real inter-cluster edges,
  writes a name + one-paragraph narrative per subsystem and one top-level
  "how this repo fits together" summary.
- Synthesis agent narrates existing verified data only — it does not
  introduce new structural claims (spot-checked during manual review, same
  as Slice 11).
- `subsystems.narrative` populated in the DB; `report.md` gains a
  "Subsystems" section (name + narrative + member modules) and a
  top-of-report overview paragraph.
- One runnable check: given fixture verified summaries + clusters, the
  renderer produces the expected Markdown structure (the synthesis agent's
  actual prose isn't unit-tested, same caveat as Slice 11).

Skipped for now: HTML site.

## Slice 13: Multi-Page HTML Site

Same data, new surface — a readable, linkable site instead of one Markdown
file, for browsing a big swept codebase.

Acceptance criteria:

- `site/index.html`: repo meta, subsystem list (name + one-line narrative +
  module count), links to each subsystem page.
- `site/subsystem-<name>.html`: subsystem narrative, its modules with each
  verified summary + evidence files + key files, and real edges within/
  leaving the subsystem.
- All pages self-contained (inline CSS, no external requests, reusing
  `html_export.py`'s existing dark-theme styles) and linked to each other
  via relative paths only.
- Same "no HTML injection" convention as the rest of Blueprint: every
  repo-derived string is escaped before embedding.
- One runnable check: fixture sweep data in, assert both pages render, no
  `<script`/external `<link`, and cross-page links resolve to real
  generated filenames.

Skipped for now: search/filter within the site, comparing two sweeps side
by side.
