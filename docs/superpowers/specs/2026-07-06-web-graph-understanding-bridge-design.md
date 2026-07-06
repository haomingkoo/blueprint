# Design: Web graph ↔ understand-repo bridge

Date: 2026-07-06
Status: approved (pending implementation plan)

## Summary

A read-only bridge between Blueprint's two previously disconnected pieces:
the web app's live interactive graph (`server/static/`, structural facts
only) and the `understand-repo` skill's verified AI layer (per-module
summaries, per-edge descriptions, a repo overview — each independently
adversarially checked before being kept). `POST /api/analyze` gains one
step: if a sweep already exists for the analyzed repo, its verified data
is merged into the response as optional fields, and the existing graph UI
renders them where present. No new LLM calls happen inside the server, and
nothing about today's structural analysis changes.

## Problem

The two systems currently don't talk to each other. The web app has the
polished pan/zoom/search graph canvas but no semantic layer; the skill has
the semantic layer but only a static HTML site, disconnected from that
canvas. A user who's already run a sweep for a repo gets no benefit from
it when they analyze that same repo in the browser.

## Relationship to existing work

- Does not change `analyzer/analyze_local_repo`, `build_graph`, or the
  skill's `sweep.py`/`semantic.py`/`synthesis.py`/`edges.py` — this is
  purely an additive read step in `server/main.py` plus additive
  rendering in the existing frontend.
- Reuses the skill's existing SQLite schema (`understanding.db`) and its
  `latest` symlink convention exactly as `understand-repo` already
  produces them — no schema changes.
- Distinct from Slice 9 (Analysis History, `docs/issues.md`), which is
  about caching the web app's own *structural* analyses to skip
  re-cloning — unrelated data, unrelated cache.

## Goals

- Analyzing a repo in the web app shows verified summaries/descriptions
  automatically, with zero extra user action, whenever a sweep already
  exists for that repo.
- Zero new LLM calls triggered by the server — the skill remains the only
  way verified data gets produced.
- Zero behavior change when no sweep exists — response shape and UI are
  identical to today.
- Every verified claim shown in the web app is traceable to the sweep it
  came from (which commit it was verified against).

## Non-goals

- No triggering a sweep from the web app (no async job handling, no LLM
  API calls added to `server/`).
- No staleness detection/warning beyond showing the sweep's own commit
  SHA — the viewer judges relevance themselves.
- No changes to the Flow Explorer view, and no changes to the skill's own
  static HTML site output (`site/`) — both are out of scope.
- No new node/edge types, no subsystem-level grouping added to the graph
  canvas — the graph's existing per-module/per-edge granularity is
  unchanged; a subsystem overview is surfaced as plain text, not a new
  graph layer.

## Architecture

`POST /api/analyze` (`server/main.py`) gains one step after building the
existing `RepoIndex`:

1. Compute the sweep's expected location:
   `<blueprint-repo-root>/.understanding/<index.repo.name>/latest/understanding.db`
   (same root the skill already writes under, same `latest` symlink
   convention `sweep.py` already maintains).
2. If that path doesn't exist (no `.db` file), skip entirely — the JSON
   response is byte-for-byte what it is today.
3. If it exists, open it read-only and pull:
   - `sweeps.overview` → response's new `understanding_overview` field
     (`null` if never set).
   - `sweeps.commit_sha` → response's new `understanding_commit_sha`
     field, always present alongside `understanding_overview` /
     any verified data, so the frontend can show "verified as of
     `<sha>`".
   - `semantic_summaries` rows → merged onto the matching `Node` (matched
     by `module:<module_name>` = `node.id`) as an optional
     `verified_summary` object (`{text, evidence_files}`), `null` if that
     module has no verified row.
   - `edge_descriptions` rows (via the skill's own
     `load_edges_with_descriptions` merge, reused directly rather than
     reimplemented) → merged onto the matching `Edge` (matched by
     `source`/`target`) as an optional `verified_description` string,
     `null` if undescribed.
4. This is read-only — no write ever happens to `understanding.db` from
   the web app, and no sweep is ever created by it.

## Matching

Matched by `repo_name` only (`index.repo.name`, e.g. `"blueprint"`) — the
web app clones to an ephemeral temp directory, so there is no stable local
path to match a sweep against; name is the only workable bridge between
"a GitHub URL was analyzed" and "a local path was swept." If more than one
sweep exists for that name, the skill's own `latest` symlink picks the
most recent — the bridge never chooses among sweeps itself.

No commit-SHA staleness check: if the repo has changed since the sweep,
the enrichment is still shown, tagged with the sweep's own
`understanding_commit_sha` so a viewer can judge relevance themselves,
rather than the server guessing whether a diff is "significant."

## UI changes

- **Node drawer** (`server/static/graph.js`): gains a "Verified" block —
  the summary text plus its evidence file list — appended after the
  existing type/files/confidence fields, rendered only when
  `node.verified_summary` is present. No existing drawer field changes.
- **Edge labels**: when `edge.verified_description` is present, the
  on-diagram label text (today: `"imports"` / `"depends on"`) is replaced
  by the verified description, reusing the exact same label-rendering
  path already in `graph.js` — no new click/drawer interaction added for
  edges.
- **Overview banner**: a short paragraph above the graph view, populated
  from `understanding_overview` when present, hidden entirely when absent
  (matches the existing `[hidden]` pattern already used elsewhere in this
  page per Slice 6/7's HANDOFF notes).
- Every one of these three additions independently degrades to "not
  shown" — a sweep with an overview but no per-module summaries still
  shows the banner and nothing else; there's no all-or-nothing gate.

## Error handling

- Missing `.understanding/` directory, missing repo-name subdirectory, or
  a broken/missing `latest` symlink: treated identically to "no sweep
  exists" — response unchanged, no error surfaced to the client.
- A `.db` file that exists but fails to open or is missing an expected
  table (e.g. a sweep from before a schema addition): caught and treated
  the same as "no sweep" — logged server-side, never a 500 to the client.
  This is the same defensive posture `server/main.py`'s existing export
  endpoints already use for malformed input.

## Testing

- `server/test_server.py` gains cases: analyzing a repo with no matching
  sweep directory returns the same shape as today (regression guard); a
  fixture sweep directory with a real `understanding.db` (module summary
  + edge description + overview) produces a response with all three
  optional fields populated and correctly attached to the right
  node/edge; a `.db` file that's present but corrupt/missing a table
  degrades to "no sweep" rather than a 500.
- Frontend: manual verification (this page has no JS test runner) — drive
  a real analyze against a repo with a real sweep in `.understanding/`,
  confirm the drawer/edge-label/banner all render, then confirm a repo
  with no sweep renders identically to before this change (no regression
  screenshot needed, but a before/after visual check is part of "done").

## Open questions / deferred

- Whether the Flow Explorer view should also surface verified data for
  the nodes/edges in a flow subgraph — deferred; the flow view reuses
  `graph.js`'s rendering primitives, so extending this later is likely
  cheap, but not scoped here.
- Whether `understand-repo`'s sweep should eventually be triggerable from
  the web app (async job) — explicitly out of scope per this design's
  Non-goals; revisit only if read-only enrichment proves not enough.
