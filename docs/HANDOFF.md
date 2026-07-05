# Handoff Log

Passdown notes between slices. Each entry is written when a slice is finished,
before context is cleared, so the next session (or sub-agent) can pick up
without re-reading the whole history.

## Template

```
## Slice N: <title> — done <date>

What shipped:
- ...

Verified:
- <runnable check> passed

Decisions made this slice (not in docs/prd.md yet):
- ...

Next slice starts from:
- ...
```

## Slice 1: Repo -> Plain-English Summary (CLI) — done 2026-07-05

What shipped:
- `analyzer/analyze.py`: clone + scan -> `RepoIndex` (repo metadata, files, language counts).
- `analyzer/report.py`: `render_markdown(index)` -> Markdown report (metadata, summary sentence, language breakdown).
- `analyzer/cli.py`: `python3 cli.py <repo-url>` prints the report.

Verified:
- `python3 test_analyze.py` and `python3 test_report.py` pass (fixture-based, no network).
- End-to-end run against `https://github.com/octocat/Hello-World` produces a correct, correctly-pluralized report.

Decisions made this slice:
- Language detection is extension-based (`LANGUAGE_BY_EXT` in `analyze.py`), not AST-based. Fine for counts; Slice 2 needs real parsing for manifests.
- No third-party deps yet — stdlib + `git` CLI only.

Next slice starts from:
- Slice 2: extend `RepoIndex`/`FileInfo` with manifest detection (`package.json`, `pyproject.toml`, `requirements.txt`, `setup.py`), entrypoint/test/config/docs classification, each with an evidence path. Extend the Markdown report with a "Detected Stack" + "Entrypoints" section.

## Slice 2: Manifests, Entrypoints, Tests in the Summary — done 2026-07-05

What shipped:
- `analyzer/analyze.py`: `FileInfo` gains a `role` field (`entrypoint`, `test`, `config`, `docs`, `unclassified`), set by `classify_role()` — a filename/path heuristic, evidence is the path itself. `RepoIndex` gains `manifests: list[Manifest]`.
- New `Manifest` dataclass (`path`, `kind`, `name`, `dependencies`, `scripts`) and `extract_manifests()`, with one parser per manifest type: `package.json` (npm, via `json`), `pyproject.toml` (PEP 621 `[project]` or Poetry `[tool.poetry]`, via stdlib `tomllib`), `requirements.txt` (line-based), `setup.py` (stdlib `ast`, reads the `setup(...)` call's `name`/`install_requires` keywords).
- `analyzer/report.py`: new "Detected Stack" section (manifest path/kind/name, dependencies capped at 10 + "N more", scripts) and "Entrypoints" section (files with `role == "entrypoint"`), both with an explicit "None detected" fallback so absence is stated, not omitted.
- `analyzer/test_slice2.py`: new runnable check — a fixture repo with one file per manifest kind plus entrypoint/test/docs/config/unclassified files, asserting exact role classification and parsed manifest contents, plus report-rendering assertions for both the populated and empty-manifest cases.

Verified:
- `python3 test_slice2.py`, `python3 test_analyze.py`, `python3 test_report.py` all pass (existing Slice 1 tests untouched and still green — `FileInfo.role` and `RepoIndex.manifests` both default so old fixtures keep working).
- End-to-end: `python3 cli.py https://github.com/octocat/Hello-World` — no manifests/entrypoints, both sections render "No ... detected" without crashing.
- End-to-end: `python3 cli.py https://github.com/jonschlinkert/is-number` — real `package.json` correctly yields dependencies (`ansi`, `benchmark`, `gulp-format-md`, `mocha`), script `test`, and entrypoints `index.js` + `benchmark/index.js`.
- End-to-end: `python3 cli.py https://github.com/pypa/sampleproject` — real `pyproject.toml` correctly yields dependency `peppercorn` and script `sample`.

Decisions made this slice (not in docs/prd.md yet):
- Role classification precedence: `config` (manifest or known config filename) > `test` > `docs` > `entrypoint` > `unclassified`. Matters because e.g. `setup.py` must land on `config`, not `entrypoint`.
- Classification is filename/path-only, no file-content sniffing beyond `setup.py`'s AST read — keeps evidence to "the path itself," per the no-fake-precision principle.
- `pyproject.toml`: PEP 621 `[project.dependencies]`/`[project.scripts]` take precedence over Poetry's `[tool.poetry.dependencies]`/`[tool.poetry.scripts]` when both are present (uncommon, but avoids double-counting).
- `setup.py` dependency extraction only handles the common case: a direct `setup(name=..., install_requires=[...])` call with literal values. Anything computed/dynamic yields empty deps rather than a guess.
- All manifest parsers catch their format-specific parse errors and fall back to an empty/blank `Manifest` rather than raising — a malformed manifest must not crash the whole analysis.
- `FileInfo.role` defaults to `"unclassified"` and `RepoIndex.manifests` defaults to `[]`, so Slice 1's existing fixtures/tests needed no changes.
- Did not add the `ignored` boolean the PRD's File model mentions — files under `IGNORED_DIRS` are already filtered out before `FileInfo` is created, and adding a redundant flag wasn't part of this slice's acceptance criteria.

Next slice starts from:
- Slice 3 (`docs/issues.md`): add review findings — severity, category, title, evidence, explanation, recommendation, confidence — covering at least missing tests around key files (cross-reference `role == "entrypoint"`/`"config"` files with no sibling `role == "test"` coverage), config/secrets risk, and dependency risk. New "Review Findings" section in the report. One runnable check per finding category against a fixture repo. No finding may claim certainty without evidence.

## Slice 3: Review Findings — done 2026-07-05

What shipped:
- `analyzer/analyze.py`: new `Finding` dataclass (`severity`, `category`, `title`, `evidence`, `explanation`, `recommendation`, `confidence`), matching the PRD's data model. `RepoIndex` gains `findings: list[Finding]`.
- `generate_findings(files, manifests) -> list[Finding]`, computed in `analyze_local_repo` from data already collected — no new file-content scanning. Three category generators:
  - `_find_missing_test_coverage`: entrypoint files with no `role == "test"` file in the same directory and no `test_<name>`/`<name>_test`/`<name>.test.*` match anywhere in the repo. Evidence = the entrypoint's path.
  - `_find_secrets_risk`: a committed `.env` with no `.env.example`/`.env.sample` anywhere in the repo. Deliberately conservative — reads no file content, never claims a secret was found, only flags the pattern and asks the user to confirm.
  - `_find_dependency_risk`: per manifest, (a) `len(dependencies) >= LARGE_DEPENDENCY_THRESHOLD` (30, heuristic), or (b) for `python-requirements`/`python-setuptools` manifests only, zero of the dependencies contain a version-specifier marker (`==`, `>=`, etc.).
- `analyzer/report.py`: new "Review Findings" section, grouped into three fixed subsections (Missing Test Coverage / Config & Secrets Risk / Dependency Risk), each rendering severity + confidence + evidence + explanation + recommendation per finding, or "No findings in this category." when empty.
- `analyzer/test_slice3.py`: new runnable check — one fixture repo triggering all three categories (uncovered `main.py`, a bare `.env`, unpinned `requirements.txt`), one for the large-dependency-list sub-case, and one clean fixture (covered entrypoint, no `.env`, pinned deps) asserting zero findings and the per-category fallback text.

Verified:
- `python3 test_analyze.py`, `python3 test_report.py`, `python3 test_slice2.py`, `python3 test_slice3.py` all pass; `pytest -q` in `analyzer/` collects and passes all 12 tests across the four files.
- `uvx ruff check analyzer/` — clean. `ty check` reports the same 2 pre-existing diagnostics as the Slice 2 baseline (unrelated to this slice's changes); no new diagnostics introduced.
- End-to-end: `python3 cli.py https://github.com/octocat/Hello-World` — no manifests/entrypoints, all three finding categories render "No findings in this category." without crashing.
- End-to-end: `python3 cli.py https://github.com/jonschlinkert/is-number` — real repo, no secrets/dependency findings, but flags `index.js` and `benchmark/index.js` as entrypoints with no detected test coverage (see decision below on a known false-positive here).
- End-to-end: `python3 cli.py https://github.com/pypa/sampleproject` — no entrypoints detected, `pyproject.toml`'s `peppercorn` dependency isn't in a pin-checkable manifest kind, so correctly no findings.
- `python3 analyze.py <url>` JSON output also serializes `findings` correctly via `asdict`.

Decisions made this slice (not in docs/prd.md yet):
- **Missing-tests check scoped to `role == "entrypoint"` only, not `role == "config"`.** The task brief said "entrypoint or config files," but `role == "config"` covers both manifests (`package.json`, `pyproject.toml`, ...) and infra dotfiles (`Dockerfile`, `tsconfig.json`, `.gitignore`, ...) — none of which are meaningfully "missing a test" in a way a reviewer would act on. Applying the heuristic there would produce near-universal noise across every analyzed repo, which conflicts with the PRD's "no fake precision" principle more than it serves the "missing tests" acceptance criterion. Flagged as a judgment call rather than guessed silently; revisit if a narrower "config" sub-role is ever introduced.
- **Confidence is `"heuristic"` for every Slice 3 finding, uniformly.** None of the three categories are backed by static analysis, a secret scanner, or a vulnerability database (explicitly out of scope) — they're all pattern checks over already-parsed data, so a single honest confidence tier avoids inventing false gradations of certainty.
- **Secrets-risk reads no file content.** Only `.env`'s presence/absence and `.env.example`/`.env.sample`'s presence/absence (both already in `RepoIndex.files`) are used. Content-based "hardcoded secret pattern" matching was in scope per the brief but deliberately dropped — it would require reading arbitrary file bytes not already captured by `RepoIndex`, and risks exactly the false "you have a leaked secret" claim the brief warned against; the `.env`-without-`.env.example` check alone satisfies the acceptance criterion without that risk.
- **Dependency pin-checking is restricted to `python-requirements` and `python-setuptools` manifest kinds.** `npm` and pyproject's Poetry branch only keep dependency *names* in `Manifest.dependencies` (version specifiers were dropped in Slice 2's parsing), so claiming "zero pinned versions" there would not be backed by real evidence — every npm/Poetry manifest would falsely show as unpinned. Only kinds whose `dependencies` strings retain the original specifier are checked.
- **Observed limitation, not fixed this slice:** `jonschlinkert/is-number`'s real test file is `test.js` (bare, no underscore/dot) — `classify_role` (Slice 2) doesn't recognize this naming convention as `role == "test"`, so the missing-tests heuristic reports a false positive for `index.js` there. This is an inherent limitation of the specified heuristic (confidence is honestly "heuristic," not a certainty claim), not a Slice 3 bug — left as-is rather than expanding `classify_role`'s test-detection patterns, which is Slice 2's surface and out of scope here.

Next slice starts from:
- Slice 4 (`docs/issues.md`): add per-module "start here" descriptions — group files into modules/components (directory-based heuristic), one paragraph per module (what it is, why it likely exists, key files), new "Key Files & Modules" / "Start Here" report section ordered by suggested read order (entrypoints first). Inference-based claims must be labeled as inference. One runnable check against a fixture repo with 2+ modules.

## Slice 4: Per-Module "Start Here" Guide — done 2026-07-05

What shipped:
- `analyzer/analyze.py`: new `Module` dataclass (`name`, `file_count`, `key_files`, `has_entrypoint`, `has_manifest`, `description`). `RepoIndex` gains `modules: list[Module]`.
- `group_into_modules(files, manifests) -> list[Module]`, computed in `analyze_local_repo` from data already collected — no new file-content scanning:
  - `_group_files_by_top_dir`: groups by the first path component; files directly at the repo root form their own `"(repo root)"` group.
  - `_select_key_files`: within a module, entrypoints rank first, then manifest/config files, then everything else (alphabetical within a tier), capped at `MAX_KEY_FILES_PER_MODULE` (5).
  - `_describe_module`: one paragraph per module — a **fact** sentence (file count, dominant language if uniform, top key file, all traceable to real paths in `files`) followed by an **inference** sentence (what the module is likely for, from an `INFERRED_MODULE_PURPOSE` directory-name lookup table, e.g. `tests` -> "test suite", `api` -> "API layer"). The inference sentence is explicitly worded as inferred ("...inferred from naming, not verified"); an unrecognized directory name gets an honest "no naming convention recognized... not inferred here" sentence instead of a guess.
  - `_module_sort_key`: suggested read order — modules with an entrypoint first, then modules with a manifest/config file, then everything else; ties broken by file count descending, then name alphabetically.
- `analyzer/report.py`: new "Start Here" section, rendered last (after Review Findings), listing modules in the precomputed read order with their description and a "Key files" line, or "No modules detected." when the repo has no files.
- `analyzer/test_slice4.py`: new runnable check — a fixture repo with 4 distinct modules (`app/` with an entrypoint, the repo root with a manifest, `tests/` with a recognized name, `widgets/` with an unrecognized name) asserting read order, that key files/facts trace to real paths, and that fact vs. inference wording differs per module; plus a flat fixture repo (no subdirectories at all) asserting it collapses to a single `"(repo root)"` module without crashing; plus an empty-repo case asserting the "No modules detected." fallback.

Verified:
- `python3 test_analyze.py`, `python3 test_report.py`, `python3 test_slice2.py`, `python3 test_slice3.py`, `python3 test_slice4.py` all pass; `pytest -q` in `analyzer/` collects and passes all 18 tests across the five files.
- `uvx ruff check analyzer/` — clean. `ty check` reports the same 2 pre-existing diagnostics as the Slice 2/3 baseline (unrelated to this slice); no new diagnostics introduced.
- End-to-end: `python3 cli.py https://github.com/octocat/Hello-World` — flat repo, no subdirectories at all; correctly collapses to one `"(repo root)"` module, renders without crashing (this also caught and fixed a subject-verb agreement bug: "1 file sit" -> "1 file sits" for the singular root-count case).
- End-to-end: `python3 cli.py https://github.com/jonschlinkert/is-number` — root module (has `index.js` entrypoint + `package.json` manifest) correctly sorts first; `benchmark/` (no naming match) sorts second with an honest "not inferred" sentence.
- End-to-end: `python3 cli.py https://github.com/pypa/sampleproject` — nested paths (`src/sample/__init__.py`) correctly group under top-level `src`; read order comes out root (manifest) -> `src` (recognized name, more files) -> `.github` / `tests` (tied file count, alphabetical tiebreak) -> matches the stated ordering rule.
- `python3 analyze.py <url>` JSON output serializes `modules` correctly via `asdict`.

Decisions made this slice (not in docs/prd.md yet):
- **Module grouping is top-level-directory only, one level deep.** A file's module key is its first path component (or `"(repo root)"` if it has none); nested subdirectories (e.g. `src/sample/`) are *not* split into their own modules — they roll up into `src`. Simpler than a "first-meaningful directory" heuristic and matches how most repos' top-level layout maps to logical components; revisit only if real repos show this rolling up too much (e.g. a monorepo with many packages under one shallow root).
- **Read-order tie-break: file count descending, then name alphabetical (case-insensitive).** Chosen so within a tier, the module a reader is statistically most likely to care about (the biggest one) surfaces first; alphabetical is just a deterministic final tiebreak, not a claim of importance.
- **Fact/inference phrasing is two sentences per module, not a uniform label prefix.** Slapping "(FACT)"/"(INFERENCE)" on every sentence read clunky in a draft pass; instead the fact sentence states only file-count/language/key-file (all directly re-derivable from `files`), and the inference sentence is the only place hedging language appears ("looks like", "inferred from naming, not verified"), or an explicit "not inferred here" when the directory name isn't recognized. Keeps the fact/inference boundary at the sentence level, which reads more naturally while still being unambiguous about which claim is which.
- **`INFERRED_MODULE_PURPOSE` is a small, fixed lookup table of common directory names** (`tests`, `api`, `src`, `models`, `docs`, `config`, ...), not content-sniffing. An unmatched name (e.g. `widgets`, `.github`) gets an honest "no naming convention recognized" sentence rather than a fabricated guess — consistent with "no fake precision."
- **`has_entrypoint`/`has_manifest` kept as `Module` fields, not just local sort-key inputs.** They're real, cheap-to-derive facts about the module (not speculative), and make the read-order rule directly testable/inspectable without re-deriving it from `files`/`manifests`.
- Manifest membership for a module is checked by exact path match against `RepoIndex.manifests` (not by role), so a module only counts as "has a manifest" if one of its files is an actually-parsed manifest, not just anything classified `role == "config"` (e.g. a bare `.eslintrc.json` doesn't count, but `package.json` does).

Next slice starts from:
- Slice 5 (`docs/issues.md`) starts **v0.2**: wrap the same analyzer + report pipeline in a FastAPI server plus a single browser page (URL input, Analyze button, loading state, rendered report as sections — Overview / Detected Stack / Start Here / Review Findings). No graph yet. The CLI/report layer built in Slices 1-4 (`analyze.py`'s `analyze_github_repo`/`analyze_local_repo` and `report.py`'s `render_markdown`) should be imported and reused as-is by the API layer — e.g. a POST endpoint that calls `analyze_github_repo(url)` and returns either the rendered Markdown or `asdict(index)` as JSON for the frontend to render. Do not reimplement analysis or rendering logic inside the API layer.
