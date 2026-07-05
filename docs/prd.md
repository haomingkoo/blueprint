# PRD: Blueprint

## Summary

Blueprint connects to a GitHub or GitLab repository, analyzes the codebase, and produces an evidence-backed interactive map that helps people understand, review, explain, and safely pick up the project.

The goal is not just a pretty architecture diagram. The product should help a user answer: "What exists here, how does data move, where should I start, and what looks risky?"

## Screenshot-Derived Direction

The reference images show an `archmap` prototype with:

- Repo URL input and `Analyze` action.
- Analysis progress states: cloning, reading imports/manifests, mapping services/stores, rendering architecture.
- Interactive dark canvas with pan/zoom.
- Nodes grouped into layers such as client, service, storage, external API, rendering, data layer, adapter layer, certs.
- Edges labeled with relationships such as `calls`, `creates Session`, `HTTP fetch`, `cache dataset to disk`, `reads CA bundle`.
- Filter chips with counts by node type.
- Right-side architecture overview.
- Node detail drawer showing type, name, technology, detected file path, and role.
- Export actions for Mermaid and PNG.
- Analysis history.

## Problem

Codebases are hard to explain because important behavior is spread across files, frameworks, dependencies, build tooling, runtime entrypoints, and undocumented conventions. New joiners, reviewers, founders, maintainers, and agents waste time building a mental model before they can safely contribute or critique.

Existing tools usually fail in one of two ways:

- Static visualizers show dependency graphs but not intent, flow, risk, or onboarding path.
- LLM summaries sound useful but are hard to verify and can invent architecture.

Blueprint should combine code-derived structure with AI explanation, but every claim must be traceable back to files, symbols, commits, or detected dependency evidence.

## Target Users

- New engineer joining a project.
- Founder or PM trying to understand a contractor-built repo.
- Senior engineer doing a codebase review.
- Agency/consultant explaining a system to clients.
- AI coding agent needing repo context before making changes.
- Maintainer writing or updating README architecture docs.

## Primary Jobs

1. Map the whole codebase at a useful level of detail.
2. Explain how requests, data, state, and external integrations move through the system.
3. Let users drill from high-level architecture to exact files and symbols.
4. Audit the repo for correctness, maintainability, security, dependency, test, and onboarding risks.
5. Export diagrams and written explanations into README, docs, or review reports.

## Product Principles

- Evidence first: every generated claim links to code evidence.
- Progressive detail: start with a high-level map, then drill into modules, files, functions, and flows.
- Review, not worship: the tool should critique unclear, risky, duplicated, or dead areas.
- Minimal setup: public repo URL should work first; auth comes after.
- Language-aware where it matters: AST/import parsing beats raw text scraping for supported languages.
- No fake precision: uncertain findings should be marked uncertain.

## MVP Scope

### 1. Repo Connection

Users can enter a public GitHub repository URL.

MVP support:

- GitHub public repos.
- Default branch detection.
- Clone or fetch source into a temporary analysis workspace.
- Ignore heavy/generated folders: `.git`, `node_modules`, `dist`, `build`, `.next`, `venv`, `__pycache__`, coverage outputs.

Later:

- GitLab.
- Private repos via OAuth or token.
- Monorepo package selection.

### 2. Static Code Index

The analyzer builds a code index containing:

- File tree.
- Languages and frameworks.
- Package manifests.
- Entrypoints.
- Imports and exports.
- Function/class/module symbols where supported.
- Internal dependencies.
- External dependencies.
- Environment/config files.
- Test files.
- Docs files.

MVP should support JavaScript/TypeScript and Python first. Unknown languages should still appear in file/module maps.

### 3. Architecture Map

The app renders an interactive graph with:

- Nodes for modules, services, routes/controllers, storage, external APIs, jobs, UI/client areas, config, and tests.
- Edges for imports, calls, route-to-handler, reads/writes, external calls, queue/job links, and test coverage links where detectable.
- Layer grouping by role.
- Filter chips by node type.
- Search by file, symbol, dependency, route, or node label.
- Right panel overview.
- Node drawer with evidence.

MVP graph can start at module/service level. Function-level graphs should exist only for selected flows, not the whole repo by default.

### 4. Flow Explorer

Users can inspect important flows:

- Request/API flow: route -> middleware -> handler -> service -> database/API -> response.
- Data flow: input -> parser/validator -> transformer -> storage/output.
- UI flow: page/component -> data fetch -> state -> render.
- Job flow: trigger -> worker -> side effect.

Each flow includes:

- Flow title.
- Diagram path.
- Plain-English explanation.
- Files and symbols involved.
- Confidence level.
- Missing/uncertain links.

### 5. Review and Critique

The app provides a codebase review report with evidence-backed findings.

MVP review categories:

- Architecture clarity.
- Coupling and dependency direction.
- Missing tests around critical paths.
- Security-sensitive code paths.
- Configuration and secrets risk.
- Error handling and retry behavior.
- Dead or suspicious unused code.
- Onboarding/documentation gaps.

Each finding must include:

- Severity.
- Evidence path and line/symbol when available.
- Why it matters.
- Suggested next action.
- Confidence.

### 6. Explanation and Onboarding

The app generates:

- "How this repo works" overview.
- "Start here" guide for new contributors.
- Key files list.
- Glossary of domain concepts found in code.
- Suggested walkthrough order.

### 7. Export

Users can export:

- Mermaid diagram.
- PNG diagram.
- Markdown architecture summary.
- Markdown code review report.

MVP: Mermaid and Markdown first. PNG can be browser-generated.

## Non-Goals for MVP

- Full semantic correctness across every language.
- Runtime tracing in deployed environments.
- Private repo auth.
- Auto-fixing code.
- Replacing human code review.
- Full function-level graph of every symbol in large repos.

## Accuracy Requirements

Generated explanations must use one of these evidence types:

- Static parser evidence: AST, imports, exports, function/class definitions.
- Manifest evidence: dependencies, scripts, framework config.
- File evidence: matched paths, filenames, docs, tests.
- Heuristic evidence: clearly labeled as heuristic.
- LLM inference: clearly labeled as inference and linked to supporting files.

Any node, edge, or review finding should be inspectable back to evidence.

## User Flow

1. User enters a repo URL.
2. App validates the URL and starts analysis.
3. App shows progress and discovered facts.
4. App opens the architecture map.
5. User filters/searches/drills into nodes.
6. User opens important flows.
7. User reads review findings.
8. User exports diagram/report.

## MVP Data Model

Minimal internal objects:

- `Repo`: provider, owner, name, branch, commit SHA, URL.
- `File`: path, language, size, role, ignored flag.
- `Symbol`: name, kind, file path, line range when available.
- `Node`: id, label, type, file paths, symbols, summary, confidence.
- `Edge`: source, target, type, label, evidence, confidence.
- `Flow`: title, nodes, edges, explanation, evidence, confidence.
- `Finding`: severity, category, title, evidence, explanation, recommendation, confidence.

## Technical Direction

Start with a local-first analyzer and simple web UI.

Suggested build order:

1. Analyze a local or public repo into JSON.
2. Render the JSON graph.
3. Add node drawer evidence.
4. Add flow extraction for one stack.
5. Add review report.
6. Add exports.

Use boring pieces:

- Git CLI for clone/fetch.
- Native filesystem scanning with ignore rules.
- Existing parsers where installed or cheap.
- Mermaid export from graph JSON.
- React Flow or a similar installed graph library only if already present when the app exists.

## Success Metrics

- User can map a public repo in under 2 minutes for a small/medium repo.
- At least 80% of displayed nodes link to concrete files.
- At least 70% of displayed edges link to concrete evidence or are marked heuristic.
- A new engineer can identify entrypoints, key flows, and top risks within 10 minutes.
- Exported Markdown is useful enough to paste into a README with minor edits.

## Milestones

Tracked as vertical slices in `docs/issues.md`. Each milestone is a working,
demoable state of the app, not a layer of the stack.

- **v0.1 — CLI review tool** (Slices 1-4): paste a repo URL, get a Markdown
  report with detected stack, review findings, and a start-here guide. No UI.
- **v0.2 — Web app** (Slice 5): same report, rendered in a browser.
- **v0.3 — Visual layer** (Slices 6-7): architecture graph and flow explorer
  added on top of the same data.
- **v0.4 — Shareable output** (Slices 8-9): export and history.

## Open Questions

- ~~Should v0 optimize for onboarding, architecture diagramming, or code review?~~
  Resolved: onboarding + review are the product; the graph is a visual layer, not the core deliverable.
- ~~Is the first product a hosted SaaS, local desktop/devtool, or CLI-plus-web app?~~
  Resolved: CLI first (v0.1), wrapped in a local web app from v0.2 onward.
- ~~Is "trustworthy review" more important than "beautiful visual map" for launch?~~
  Resolved: yes — see Slice ordering in `docs/issues.md`.
- Which stack should be first-class first: JS/TS web apps, Python packages, or both?
- What repo size should v0 handle without timing out?
- How much LLM usage is acceptable per repo analysis?
- Should users be allowed to edit/correct the generated map?
