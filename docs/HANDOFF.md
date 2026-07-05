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
