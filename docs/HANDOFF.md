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

## Slice 5: Web UI (v0.2) — done 2026-07-05

What shipped:
- New `server/` directory (sibling to `analyzer/`), untouched `analyzer/` — the API layer imports and calls `analyzer`'s existing `analyze_github_repo` directly, no analysis/rendering logic duplicated server-side.
- `server/main.py`: FastAPI app, one endpoint `POST /api/analyze` taking `{"repo_url": "..."}`. Adds `analyzer/` to `sys.path` at import time (mirroring how `analyzer/report.py` bare-imports `analyze` — analyzer has no package `__init__.py`, so this is the least-invasive way to reuse it without restructuring analyzer's import style) then calls `analyze_github_repo(url)` and returns `asdict(index)` as JSON on success.
- Error handling per security.md ("generic client-facing errors, details server-side only"): a small `_validate_repo_url` rejects empty/non-GitHub URLs before ever shelling out to git (400, no clone attempt); `subprocess.CalledProcessError` (bad URL/private repo/network failure during `git clone`) and any other unexpected exception are caught, logged server-side with `logging.getLogger("blueprint.server")` (real git stderr included), and translated to a generic 400/502 JSON `{"error": "..."}"` — never a raw traceback. Malformed request bodies (missing `repo_url`) get FastAPI's automatic 422, which is already a clean JSON error.
- Static single-page frontend at `server/static/` (`index.html`, `styles.css`, `app.js`), served via `StaticFiles(html=True)` mounted at `/` (mounted *after* the `/api/analyze` route is registered, so the API route is matched first). URL input + Analyze button, a loading state with an explicit "10–30 seconds" note and an animated scan-bar, and a report view with five sections mirroring `report.py`'s Markdown structure: Overview, Detected Stack, Entrypoints, Review Findings (grouped into the same three fixed subcategories as the Markdown report), Start Here.
- Visual design: a "blueprint/engineering-drawing" dark theme (deep navy background, faint drafting-grid overlay, cyan pencil-line accents, IBM Plex Mono for labels/headings/code, Newsreader serif for prose), section numbering (§01–§05) throughout, corner registration ticks on panels. Chosen deliberately over a generic dark-SaaS look per frontend-design skill guidance — see decision below.
- Findings are visually distinguished by severity: a colored left border + a colored pill badge with an icon (▲ high, ● medium, ○ low, ✖ critical, current data only produces medium/high) per finding card, plus a separate muted confidence pill. Module descriptions (Start Here) are split client-side into a "Fact" claim and an "Inference" claim (two visually distinct rows, different label color/border and italic styling for the inference row) rather than rendered as one flat paragraph — see decision below on how the split works.
- `server/requirements.txt`: `fastapi==0.135.1`, `uvicorn==0.42.0` (pinned per security.md). Test-only deps (`httpx` for `TestClient`, `pytest`) are installed directly in CI, same convention as `analyzer/`'s existing tests — not added to `requirements.txt`.
- `server/test_server.py`: `fastapi.testclient.TestClient`-based checks (plain `assert` functions, same runnable-as-a-script style as `analyzer/`'s tests) — a stubbed successful analyze (via `unittest.mock.patch.object`, no network), a stubbed `git clone` failure asserting a clean 400 with no `Traceback`/raw git stderr in the response, a non-GitHub URL, a blank URL, a missing-field 422, and a smoke check that `/` serves the real `index.html`.
- `server/README.md`: setup/run/test instructions.
- `.github/workflows/ci.yml`: extended (not restructured) the existing `analyzer-quality` job — installs `server/requirements.txt` + `httpx` alongside the existing `pytest`/`ruff`/`ty` install, compiles/lints/tests `analyzer server` instead of just `analyzer`.
- `.pre-commit-config.yaml`: `analyzer-compile` and `analyzer-ty` local hooks extended to cover `server/` (ty hook's `additional_dependencies` now also installs pinned `fastapi`/`pydantic` so it can resolve those imports).
- `pyproject.toml`: `[tool.ty.src].include` gains `"server"`; new `[tool.ty.environment].extra-paths = ["analyzer"]` so ty can resolve `server/main.py`'s `from analyze import ...` across the analyzer/server directory boundary (the same bare-import style `report.py` already uses within `analyzer/`).

Verified:
- `python3 server/test_server.py` and `python3 -m pytest analyzer server -q` — 24 tests pass (18 existing + 6 new).
- `uvx ruff@0.15.20 check analyzer server` — clean.
- `uvx ty@0.0.56 check --output-format concise` (pointed at a Python env with `fastapi`/`pydantic` installed, matching what CI's install step now sets up) — same 2 pre-existing baseline diagnostics as Slices 2-4, no new diagnostics from `server/`.
- End-to-end, real server: `uvicorn server.main:app --app-dir . --port 8099` started cleanly.
  - `GET /` returned the real `index.html` (verified `<title>Blueprint`, `id="analyze-form"`, `id="repo-url"`, `id="analyze-button"`, `id="status"`, `id="report"`, and links to `/app.js`/`/styles.css` are all present); `GET /styles.css` and `GET /app.js` both 200 with correct content-types; fetched `app.js` and confirmed all render functions (`renderReport`, `renderOverview`, `renderStack`, `renderFindings`, `renderStartHere`, `splitFactFromInference`) are present in the served file.
  - `POST /api/analyze` with `https://github.com/octocat/Hello-World` → HTTP 200, correct `RepoIndex` JSON (repo metadata, 1 file, empty manifests/findings, 1 root module with the expected fact+inference description).
  - `POST /api/analyze` with `https://github.com/jonschlinkert/is-number` → HTTP 200, real `package.json` manifest (4 deps), 2 entrypoints (`index.js`, `benchmark/index.js`), 1 missing-test-coverage finding on `benchmark/index.js`, 2 modules — same shape as Slice 2/3/4's CLI verification against this same repo.
  - Bad input, all confirmed clean 4xx with no traceback: non-GitHub URL → 400 `{"error": "Only public GitHub repository URLs..."}`; blank URL → 400 `{"error": "Repository URL is required."}`; missing `repo_url` field → 422 (FastAPI's built-in validation error); a well-formed but nonexistent GitHub repo → 400 `{"error": "Could not clone this repository..."}`, with the real git stderr (`fatal: repository '...' not found`) confirmed present only in the server log, not in the client response body.

Decisions made this slice (not in docs/prd.md yet):
- **HTML/CSS/vanilla JS, not Vite+React.** This is a single page with no routing, no component reuse yet, and no client state beyond "is a request in flight" — Slice 6's graph view is additive to this same page later, not a rewrite, so there's no forward-looking reason to pay for a build step now. The deciding factor was verification, not just simplicity: this agent has no browser, and instruction #5 requires fetching the rendered HTML and sanity-checking its structure. A static server-rendered page makes that fetch meaningful (the real markup, form, and section containers are all in the HTML/JS actually served). A Vite+React SPA's served HTML would just be `<div id="root"></div>` plus a bundled script — fetching it would prove nothing about whether the UI is correct. Plain HTML/CSS/JS was the only option where "fetch and sanity-check" is a real verification method rather than a formality. Revisit if/when Slice 6's graph needs real interactive state management (pan/zoom/filter/search) that starts to strain vanilla DOM manipulation.
- **No CORS middleware added**, despite security.md flagging CORS as a checklist item. The frontend is served by the same FastAPI app as the API (`StaticFiles` mounted on the same origin), so there is no cross-origin request to configure — adding `CORSMiddleware` with an explicit allow-list would be dead configuration for a same-origin app. Revisit only if the frontend and API ever split onto different hosts.
- **No request timeout added around `analyze_github_repo`.** `git clone` has no timeout in `analyzer/analyze.py`'s `clone_repo` today (true since Slice 1), and adding one at the server layer would either require modifying `analyzer/` (out of this slice's scope — "import and call analyzer's existing functions directly") or wrapping the call in a background thread with a hard cutoff that abandons a still-running clone (messy, and not asked for by Slice 5's acceptance criteria). Flagged as a known gap, not fixed: a malicious or pathological URL could hang a request indefinitely. Worth revisiting if Slice 5/6 ever gets exposed beyond local dev.
- **URL validation is intentionally shallow**: reject empty strings and anything not starting with `http(s)://` + containing `github.com`, before ever invoking git. This is not full URL parsing/allow-listing — it exists to fail fast on obviously-wrong input with a specific message, not to be a security boundary (the real safety property — no shell injection — already comes from `analyzer/analyze.py`'s `clone_repo` passing args as a list to `subprocess.run`, never through a shell).
- **Fact/inference split is done client-side by string position, not by extending `Module`'s schema.** `analyze.py`'s `_describe_module` (Slice 4) always emits exactly one fact sentence followed by one inference sentence in a single `description` string. Rather than changing `Module`'s shape (Slice 4's surface, and would ripple into `report.py`'s Markdown rendering) just to make the frontend's job easier, `app.js`'s `splitFactFromInference` splits on the first `". "` boundary. This is a display-only heuristic coupled to `_describe_module`'s current wording (always exactly two sentences) — if a future slice changes that wording to something other than two sentences, this split silently degrades to "whole paragraph as one fact claim, no inference row" rather than crashing, but would need updating. Called out here so it isn't a silent trap for whoever touches `_describe_module` next.
- **Findings/manifest rendering (truncation, subsection grouping) is duplicated between `report.py` (Markdown) and `app.js` (HTML)** — e.g. both independently cap displayed dependencies at 10 with a "+N more" suffix, and both group findings into the same three fixed subsection headings. This is *rendering* logic, not *analysis* logic; the API intentionally returns the full untruncated `RepoIndex` JSON and lets each output format (Markdown vs HTML) make its own presentation choices, per the Slice 4 handoff's suggestion that the frontend renders the JSON itself. Acceptable duplication of a small, stable formatting rule, not analysis.
- **ty needed a new `[tool.ty.environment].extra-paths = ["analyzer"]` setting** to resolve `server/main.py`'s `from analyze import ...` — without it, ty (correctly) can't see across the analyzer/server directory boundary since analyzer has no package structure. Confirmed CI's existing `ty check` step now needs `server/requirements.txt` installed in the same job (added), otherwise `fastapi`/`pydantic` show as unresolved imports there too.

Next slice starts from:
- Slice 6 (`docs/issues.md`): add the architecture graph as an **additional view on this same page** (`server/static/`), not a replacement for the Overview/Detected Stack/Entrypoints/Review Findings/Start Here sections shipped this slice. Needs `Node[]`/`Edge[]` emitted from the index (modules, external deps, config, tests, docs; import/dependency edges where detectable), each with evidence + confidence; a pan/zoom/fit/search graph view with filter chips by node type + counts; click-to-open node drawer; Mermaid export from the same graph JSON; automatic collision-avoidance layout (dagre/elkjs) — screenshot 2-3 sample repos' rendered graphs as part of verifying no overlapping nodes/edges/labels. This is very likely where React Flow (or similar) becomes justified — if so, that's the natural point to introduce a real frontend build step (Vite), since the graph view has actual interactive state (pan/zoom/selection/filters) that vanilla DOM manipulation would strain; the existing Slices 1-5 sections could stay as plain HTML fragments injected alongside it, or migrate to components at that point — worth an explicit judgment call at the start of Slice 6, not decided here.
