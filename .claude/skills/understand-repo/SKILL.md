---
name: understand-repo
description: Sweeps a local repo path (no GitHub/GitLab needed -- works on any local directory), clusters its modules into subsystems by real import relationships, produces a verified per-module summary and per-edge semantic description for each one -- an agent writes a claim citing evidence files, a second independent agent tries to refute it, and only unrefuted claims survive -- then synthesizes a whole-repo narrative and builds a browsable, clickable HTML site with a Mermaid diagram. Writes a versioned, queryable sweep (SQLite + report.md + site/) under .understanding/<repo-name>/ at the Blueprint repo root, gitignored so it never leaks to GitHub. Use whenever the user wants a structural map or trustworthy summary of an unfamiliar codebase, asks to "sweep"/"cluster"/"map"/"understand" a repo, or wants a starting point for a code-handover / onboarding doc.
---

# Understand Repo

Five phases, run in order. All reuse Blueprint's existing structural
analyzer (`analyzer/analyze.py`) as ground truth — nothing here re-parses
files the analyzer hasn't already scanned. Works purely on a local
filesystem path; a repo never needs to be hosted on GitHub/GitLab, and
`.understanding/` (all sweep output) is gitignored so nothing generated
here can leak to a remote.

## Phase 1: structural clustering (Slice 10, no LLM)

```bash
python3 .claude/skills/understand-repo/scripts/sweep.py <path-to-local-repo>
```

Groups modules into subsystems via connected components over `"imports"`
edges only (`"depends_on"` edges to manifests never merge modules
together) — deterministic, reproducible. A module with no inter-module
edges becomes its own singleton subsystem.

Prints the detected subsystems and, for each module, its key evidence
files (needed by Phase 2). Writes a new timestamped sweep to
`.understanding/<repo-name>/<timestamp>-<sha>/understanding.db` at the
Blueprint repo root, and updates the `latest` symlink for that repo.
Re-running never overwrites a previous sweep.

## Phase 2: verified per-module summaries (Slice 11)

For every module worth summarizing (skip pure housekeeping/cache
directories — a "semantic summary" of `.ruff_cache` has no value), run the
Agent A / Agent B verification loop as an `ultracode` Workflow, using
`pipeline(modules, summarizeStage, refuteStage)` so modules move through
independently rather than waiting on each other:

1. **Agent A (summarize)**: given a module's name and its evidence files
   (from Phase 1's printed key files), read only those files and write one
   short paragraph on what the module does and why it likely exists.
   Nothing not directly visible in the files — if the files don't make the
   purpose clear, say so instead of inventing one.
2. **Agent B (refute)**: a fresh subagent, with no visibility into how
   Agent A produced its claim — only the claim text and the same evidence
   files. Tries to find anything in the files that contradicts or isn't
   supported by the claim. Defaults to `refuted=true` when unsure.
3. Only claims Agent B fails to refute are kept. An agent call that fails
   outright, or gets refuted, is dropped — never invented, never silently
   patched over.
4. For each kept claim, write it to a JSON payload file (using the Write
   tool, not shell interpolation — `summary_text` is LLM-written and
   `evidence_files` are real paths from the repo being swept, and the repo
   being swept is not trusted, so neither is safe to embed directly in a
   shell command line):
   ```json
   {"module_name": "<module_name>", "summary_text": "<summary_text>", "evidence_files": ["<evidence_file>", "..."]}
   ```
   then persist it:
   ```bash
   python3 .claude/skills/understand-repo/scripts/semantic.py add <sweep_dir> <payload_json_path>
   ```

A missing summary is always safer than a fabricated one — that's the
entire point of the two-agent split, and it repeats in every later phase.

## Phase 3: subsystem synthesis (Slice 12)

One synthesis agent — not a Workflow fan-out, since there's exactly one
synthesis step per sweep — given ONLY the verified per-module summaries
(Phase 2), the cluster assignments (Phase 1), and real `depends_on` edges,
writes a short human name + one-paragraph narrative per subsystem that has
verified data, plus one top-level "how this repo fits together" overview.
It must not introduce any structural claim beyond what it was given.

Persist and render, again via JSON payload files rather than inline shell
arguments (this text is LLM-written, so it never gets embedded directly in
a shell command line):
```bash
# overview-payload.json: {"overview": "<overview>"}
python3 .claude/skills/understand-repo/scripts/synthesis.py set-overview <sweep_dir> <overview_payload_json_path>
# subsystem-payload.json: {"subsystem_id": "<subsystem_id>", "name": "<name>", "narrative": "<narrative>"}
python3 .claude/skills/understand-repo/scripts/synthesis.py update-subsystem <sweep_dir> <subsystem_payload_json_path>
python3 .claude/skills/understand-repo/scripts/synthesis.py report <sweep_dir>   # writes report.md
```

A subsystem with no verified module summary is left alone (no narrative
written for it) rather than the agent inventing a "not verified" sentence
— the renderer's own fallback already says that honestly.

## Phase 4: verified per-edge semantic descriptions (Slice 14)

Same Agent A/B pattern as Phase 2, applied to real `"imports"` edges
instead of modules — this is what turns a generic "module A imports
module B" label into something like "calls `formatHeaders()` from utils to
build the request." Run as an `ultracode` Workflow, `pipeline(edges,
describeStage, verifyStage)`:

1. **Agent A (describe)**: given one edge's evidence files (the real files
   where the import was detected — already in the `edges` table), read
   them and write ONE concrete, checkable sentence about what the
   connection actually does — not a restatement of "it imports it", a real
   behavioral claim (what symbol, how it's used, if visible). If the files
   don't make the specific usage clear, say so instead of guessing.
2. **Agent B (refute)**: fresh context, only the claim + the same evidence
   files. Tries to find anything overstated or unsupported — e.g. a
   function name that doesn't actually appear. Defaults to refuted when
   unsure.
3. Only unrefuted claims are kept. Write a JSON payload file rather than
   passing this inline (`description` is LLM-written and `evidence_files`
   are real paths from the untrusted swept repo):
   ```json
   {"source": "<source_node_id>", "target": "<target_node_id>", "description": "<description>", "evidence_files": ["<evidence_file>", "..."]}
   ```
   then persist it:
   ```bash
   python3 .claude/skills/understand-repo/scripts/edges.py add <sweep_dir> <payload_json_path>
   ```
   An edge with no verified description simply keeps its existing plain
   label (`"imports"`/`"depends on"`) — never silently replaced with an
   unverified guess. `edges.py list <sweep_dir>` prints every edge with its
   description if it has one.

Not every edge needs describing — pick the ones that carry real
architectural weight (e.g. cross-module imports), not every trivial one.

## Phase 5: multi-page HTML site (Slice 13)

```bash
python3 .claude/skills/understand-repo/scripts/site.py <sweep_dir>
```

Builds `site/index.html` (repo overview + a **clickable Mermaid diagram**
of the subsystem graph — one box per subsystem, colored green if it has a
verified summary, real `depends_on` edges to manifest nodes, each
subsystem box links via Mermaid's `click` directive to its own page) and
one `site/<slug>.html` per subsystem (full narrative, member modules with
verified summary + evidence or an honest "not verified" note, a **Files**
table listing every real file in the subsystem with its structural role +
language, and real edges touching the subsystem). Self-contained: inline
CSS reused from `analyzer/html_export.py`'s dark theme, `mermaid.js`
vendored locally (`scripts/vendor/`) — no CDN, works fully offline.

No file-to-file edges are ever drawn: the analyzer only tracks imports at
module granularity (same-module imports are dropped in `build_graph`), so
inventing a specific target file for a file-to-file connection would be a
guess, not a fact.

## Data model (`understanding.db`)

- `sweeps`: one row per sweep (repo path/name, commit sha, branch, timestamp, overview).
- `subsystems`: one row per detected subsystem (id, sweep_id, name, narrative).
- `module_subsystem`: join table, one row per (module, subsystem) pairing.
- `modules`: one row per module (key_files).
- `module_files`: one row per real file (module_name, path, role, language).
- `edges`: a straight dump of the structural graph's edges (source, target, type, label, evidence).
- `semantic_summaries`: one row per **verified** per-module claim only.
- `edge_descriptions`: one row per **verified** per-edge claim only.

A row's absence from `semantic_summaries`/`edge_descriptions` always means
"not verified this sweep" — never distinguished from "never attempted" in
the rendered output, since a reader only needs to know a claim isn't
trustworthy yet, not why.

## Scope / known limitations

- Clustering quality on a much larger/messier codebase is an open
  question (a shared "hub" module can over-merge; a missed import style
  can over-fragment) — deliberately deferred per the PRD until observed
  on a real large repo, not solved speculatively.
- This skill's output is standalone files, not wired into Blueprint's own
  live web app graph (`server/static/`) — a real gap noted during
  development (the web app has the polished interactive canvas but no
  subsystem/semantic layer; this skill has the semantic layer but no live
  canvas) — worth unifying in a future slice.
