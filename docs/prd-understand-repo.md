# PRD: Understand-Repo Skill

## Summary

A Claude Code skill, shipped inside this repo, that sweeps a local repo path
and produces a verified, logically-grouped semantic understanding of the
whole codebase on top of Blueprint's existing structural analysis. It
answers "what does each part of this codebase actually do, and how does it
all fit together" — a question Blueprint's structural graph (Slices 1-8)
deliberately never claims to answer, since it only reports observed facts
and regex-detected imports.

## Problem

A big, unfamiliar codebase doesn't add up to a mental model just from a
module list and an import graph — a reader still has to do the work of
figuring out what each part means and how the pieces relate. LLM summaries
can answer that, but they're hard to trust: a single-pass LLM narrative can
sound confident and still be wrong, and there's no way to tell which parts
are grounded and which are invented. This skill adds the narrative layer
without weakening the accuracy guarantee that makes Blueprint's existing
output trustworthy — every semantic claim is independently verified against
real code before it's kept, or it's dropped.

## Relationship to Blueprint (Slices 1-8)

This reuses Blueprint's existing analyzer as ground truth rather than
duplicating it:

- The structural pass calls `analyzer.analyze_local_repo` directly (same
  function `server/main.py` already imports).
- Subsystem grouping uses the existing `Node`/`Edge` import graph
  (`build_graph`) as its objective backbone.
- Distinct from Slice 9 (Analysis History, which caches *structural* JSON to
  skip re-cloning) — this skill's sweep history is a separate, additive
  history of the *semantic* layer.
- Not a continuation of the web app's Slice numbering — a separate tool
  that ships in the same repo and depends on its analyzer.

## Target Users

- AI coding agent (Claude Code itself) needing deep context before making
  changes in an unfamiliar repo.
- Engineer or founder dropped into a large, undocumented codebase.
- Senior engineer doing a deep-dive review who wants a starting narrative,
  not just a file tree.

## Primary Jobs

1. Sweep a local repo path and produce module-level semantic summaries,
   each independently verified against real code before being kept.
2. Group modules into logical subsystems using real import relationships,
   not guesswork.
3. Synthesize a top-level narrative of how the subsystems connect.
4. Persist every sweep as history (queryable + human-readable), not
   overwrite it.

## Product Principles

- **Verify before claiming**: every semantic claim must survive an
  independent adversarial check against the actual code, or it's dropped —
  never silently invented, matching Blueprint's existing "no fake
  precision" principle.
- **Structural backbone, semantic narrative on top**: clustering and the
  base graph are deterministic and reproducible; only the *narrative* on
  top is LLM-authored, and it can't introduce new structural claims.
- **Zero new runtime dependencies**: stdlib `sqlite3`, existing Workflow
  tool, existing analyzer.
- **History over overwrite**: every sweep is a new dated snapshot.

## MVP Scope

### 1. Structural Reuse (no new work)

Calls `analyzer.analyze_local_repo(path)` directly for the existing
`RepoIndex` (files, manifests, modules, nodes, edges). No new file-content
scanning at this layer.

### 2. Clustering

Groups module-type nodes into subsystems via connected components over the
existing `"imports"` module→module edges — deterministic, reproducible, no
LLM involved. A module with no inter-module edges becomes its own singleton
subsystem.

### 3. Semantic Fan-Out & Verification

One pipeline stage per module: Agent A writes a summary citing specific
evidence files; Agent B independently re-reads the same files and attempts
to refute it. Only claims Agent B can't refute are kept, tagged
`confidence="semantic"`.

### 4. Synthesis

One agent, given only the verified per-module summaries, cluster
assignments, and real inter-cluster edges, writes a name + narrative per
subsystem and a top-level "how this repo fits together" summary. It
narrates existing verified data — it cannot introduce new structural
claims.

### 5. Persistence & Output

Every sweep is versioned under `blueprint/.understanding/<repo-name>/
<timestamp>-<sha>/`: a SQLite DB (queryable), a Markdown report, and a
multi-page self-contained HTML site (an overview page + one page per
subsystem).

## Non-Goals

- Not a replacement for Blueprint's existing structural graph/report/export
  — sits alongside it, reuses it as ground truth.
- No cross-repo comparison.
- No incremental/partial re-sweep — a re-run is always a full sweep.
- No new node/edge types beyond what `analyze.py` already detects.
- No general-purpose doc generator for non-code content.

## Accuracy Requirements

Extends Blueprint's existing two confidence tiers with a third:

| Tier | Meaning |
|---|---|
| `structural` | Directly observed (a file/dir/manifest exists) |
| `heuristic` | Regex-inferred (import scanning) |
| `semantic` (**new**) | LLM-derived, independently adversarially verified against real code |

A `semantic` claim is never surfaced — in the DB, Markdown, or HTML —
without having survived an independent refutation attempt. A module where
every claim is refuted still appears with its structural facts and an
explicit "no verified semantic summary this sweep" note; it is never
silently dropped from output.

## User Flow

1. User runs `/understand-repo <local-repo-path>`.
2. Skill runs the structural pass (existing analyzer).
3. Skill clusters modules into subsystems.
4. Skill fans out per-module semantic summarization + adversarial
   verification.
5. Skill synthesizes subsystem narratives + a top-level summary.
6. Skill writes the SQLite DB, Markdown report, and HTML site under a new
   timestamped sweep directory; updates the `latest` pointer.
7. User opens the HTML site or queries the DB directly.

## MVP Data Model

- `Sweep`: id, repo_path, repo_name, commit_sha, branch, started_at,
  finished_at.
- `Module`, `Node`, `Edge`: mirror Blueprint's existing dataclasses
  (plus `sweep_id`) — a straight dump of `RepoIndex`, nothing new claimed.
- `Subsystem`: sweep_id, name, narrative.
- `ModuleSubsystem`: sweep_id, module_name, subsystem_id (join table).
- `SemanticSummary`: sweep_id, module_name, summary_text, evidence_files,
  verified, confidence="semantic" — only rows that survived verification
  exist here.

## Technical Direction

Suggested build order (tracer-bullet, same philosophy as Slices 1-9 —
prove the analysis before building the visual layer):

1. Clustering + SQLite persistence + versioned sweep directories, CLI
   output only, no LLM yet.
2. Verified per-module semantic summaries, added to the Markdown report.
3. Subsystem synthesis narrative, added to the Markdown report.
4. Multi-page HTML site on top of the same (already-verified) data.

Use boring pieces: stdlib `sqlite3`, the existing Workflow tool for agent
fan-out/verification, `analyzer/html_export.py`'s existing dark-theme CSS
reused for the new site.

## Success Metrics

- Zero unverified semantic claim ever appears in any output (DB, Markdown,
  or HTML) — enforced by construction, spot-checked during manual review.
- Subsystem clustering matches a human's intuitive grouping on at least 2
  sample repos reviewed by hand.
- A sweep of a real medium-sized repo completes and produces a Markdown
  report + HTML site a new reader can navigate without opening the DB.

## Milestones

Tracked as vertical slices in `docs/issues.md`, Slices 10-13, continuing
directly from the existing Slice 1-9 backlog.

## Open Questions

- Whether a module should ever belong to more than one subsystem (currently
  no — connected components gives a strict partition). Revisit only if a
  real repo's clustering looks wrong in practice.
- No UI/command for browsing sweep history yet beyond the `latest` pointer
  and querying the DB directly — deferred until there's a concrete need to
  compare sweeps over time.
