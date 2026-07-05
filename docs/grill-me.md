# Grill Session: Blueprint

This is the pressure test before building. Default answers are included so we can move without waiting, but the questions should be revisited before implementation.

## 1. Are we building a diagram tool or a code review tool?

If it is a diagram tool, the MVP is graph rendering and export.

If it is a review tool, the MVP is evidence, confidence, findings, and traceability.

Default: build a repo understanding and review tool. The diagram is the main interface, not the product.

## 2. What is the first impossible promise we must avoid?

"Map the entire codebase in great detail" can become impossible if it means perfect function-level semantic understanding across all languages.

Default: map the whole repo at module/service/file level, then provide detailed flow drilldowns for selected paths.

## 3. What makes this trustworthy?

Users will not trust a beautiful graph if it cannot show why each node, edge, or critique exists.

Default: every node, edge, summary, flow, and finding needs evidence or an explicit uncertainty label.

## 4. Who is the first user?

Different users want different outputs:

- New joiner wants "where do I start?"
- Reviewer wants "what is risky?"
- Founder wants "what did someone build?"
- Maintainer wants "how do I document this?"

Default: first user is a technical reviewer onboarding to an unfamiliar repo.

## 5. What is the smallest impressive demo?

A public repo URL goes in. The app shows:

- High-level architecture graph.
- Entry points.
- Key flows.
- Node detail with file evidence.
- Three useful review findings.
- Mermaid/Markdown export.

Default: use two benchmark repos, one JS/TS app and one Python package.

## 6. Where do mistakes hurt most?

Mistakes hurt most in security findings, data flow claims, and "this code is unused" claims.

Default: mark risky inferences as low confidence unless backed by strong evidence.

## 7. What should we not build first?

Do not start with GitLab auth, private repos, runtime tracing, auto-fixes, multi-user collaboration, or a complex plugin system.

Default: public GitHub URL only.

## 8. How detailed is "great detail"?

Useful detail means the user can drill down:

- System map.
- Package/module map.
- File/symbol evidence.
- Important flow.
- Source line or symbol reference.

Default: not every function appears on the global canvas; function-level detail appears inside selected flows and node drawers.

## 9. How do we prevent LLM hallucination?

The analyzer should produce structured facts first. The LLM explains and critiques those facts, not raw-generate the map from a repo dump.

Default: static index -> graph JSON -> LLM summaries/findings with evidence -> UI.

## 10. What will users compare us against?

They will compare against:

- Reading README and code manually.
- GitHub code search.
- Sourcegraph/Cody style codebase search.
- Dependency graph tools.
- Mermaid diagrams written by humans.
- Asking ChatGPT/Claude to summarize the repo.

Default: win by combining visual map, evidence, and critique in one place.

## 11. What is the first scary scale problem?

Large repos will produce noisy graphs, slow analysis, and too many findings.

Default: cap initial graph complexity and summarize clusters. Let users expand.

## 12. What is the product's sharp claim?

Bad claim: "AI understands your whole codebase."

Better claim: "Connect a repo and get an evidence-backed architecture map, walkthrough, and review report."

Default: use the better claim.

## 13. What should the first issue not do?

The first issue should not build auth, a full SaaS shell, or a complex persistent backend.

Default: build a local analyzer that outputs graph JSON from one public GitHub repo.

## 14. What needs human correction?

Architecture labels, domain concepts, and risk severity may need user correction.

Default: v0 can expose uncertainty. Editing/correction comes after core mapping works.

## 15. What is the core risk?

The product can become a slick frontend wrapped around weak analysis.

Default: invest first in a boring, testable analysis pipeline and evidence model.

## Decision Checklist

- First repo provider: GitHub public repos.
- First analysis depth: file/module/service graph plus selected flow detail.
- First language focus: JS/TS and Python.
- First UI: repo input, graph canvas, filters, overview, node drawer, findings panel, exports.
- First trust feature: evidence links and confidence labels.
- First skipped features: GitLab, private auth, live runtime tracing, auto-fix, collaboration.
