// Blueprint — vanilla JS frontend. Calls POST /api/analyze and renders the
// returned RepoIndex JSON as report sections mirroring report.py's Markdown
// structure (Overview, Detected Stack, Entrypoints, Review Findings, Start
// Here). No framework, no build step — DOM nodes only, text content only
// (never innerHTML with server data), so nothing from an analyzed repo's
// file paths/names can inject markup.

const FINDING_CATEGORIES = [
  ["missing-tests", "Missing Test Coverage"],
  ["secrets-risk", "Config & Secrets Risk"],
  ["dependency-risk", "Dependency Risk"],
];

const SEVERITY_ICON = { critical: "✖", high: "▲", medium: "●", low: "○" };

const form = document.getElementById("analyze-form");
const input = document.getElementById("repo-url");
const button = document.getElementById("analyze-button");
const statusEl = document.getElementById("status");
const reportEl = document.getElementById("report");
const viewTabs = document.getElementById("view-tabs");
const graphViewEl = document.getElementById("graph-view");

form.addEventListener("submit", onSubmit);
viewTabs.querySelectorAll(".view-tab").forEach((tab) => {
  tab.addEventListener("click", () => setActiveView(tab.dataset.view));
});

async function onSubmit(event) {
  event.preventDefault();
  const repoUrl = input.value.trim();
  if (!repoUrl) return;

  setLoading();
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_url: repoUrl }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      setError((data && data.error) || `Analysis failed (HTTP ${response.status}).`);
      return;
    }
    setIdle();
    renderReport(data);
    if (window.BlueprintGraph) window.BlueprintGraph.render(data);
    viewTabs.hidden = false;
    setActiveView("report");
  } catch (err) {
    setError("Could not reach the analyzer. Check the server is running and try again.");
  }
}

function setLoading() {
  button.disabled = true;
  reportEl.replaceChildren();
  viewTabs.hidden = true;
  statusEl.replaceChildren(
    el("div", { className: "status-loading" }, [
      document.createTextNode(
        "Cloning and analyzing the repo — this can take 10–30 seconds…"
      ),
    ]),
    el("div", { className: "scan-bar" })
  );
}

function setActiveView(view) {
  viewTabs.querySelectorAll(".view-tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === view);
  });
  reportEl.hidden = view !== "report";
  graphViewEl.hidden = view !== "graph";
  // The graph's own initial fit-to-view runs while this tab is still
  // hidden (zero-size container), so it's a no-op then — re-fit now that
  // the SVG has real dimensions.
  if (view === "graph" && window.BlueprintGraph) window.BlueprintGraph.fit();
}

function setIdle() {
  button.disabled = false;
  statusEl.replaceChildren();
}

function setError(message) {
  button.disabled = false;
  statusEl.replaceChildren(el("div", { className: "status-error", text: message }));
}

// ---------- DOM helpers ----------

function el(tag, opts, children) {
  const node = document.createElement(tag);
  opts = opts || {};
  if (opts.className) node.className = opts.className;
  if (opts.text != null) node.textContent = opts.text;
  if (opts.attrs) {
    for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
  }
  for (const child of children || []) {
    if (child != null) node.appendChild(child);
  }
  return node;
}

function section(index, title, children) {
  return el(
    "section",
    { className: "report-section" },
    [
      el("h2", { className: "section-heading" }, [
        el("span", { className: "tag-index", text: `§${index}` }),
        document.createTextNode(title),
      ]),
      ...children,
    ]
  );
}

function codeChip(text) {
  return el("code", { className: "code-chip", text });
}

function pluralize(count, noun) {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

// ---------- Section renderers ----------

function renderReport(index) {
  reportEl.replaceChildren(
    section("01", "Overview", renderOverview(index)),
    section("02", "Detected Stack", renderStack(index.manifests)),
    section("03", "Entrypoints", renderEntrypoints(index.files)),
    section("04", "Review Findings", renderFindings(index.findings)),
    section("05", "Start Here", renderStartHere(index.modules))
  );
}

function renderOverview(index) {
  const repo = index.repo;
  const languages = Object.entries(index.language_counts).sort((a, b) => b[1] - a[1]);
  const topLanguage = languages.length ? languages[0][0] : "unknown";
  const totalFiles = index.files.length;

  const meta = el("div", { className: "overview-meta" }, [
    el("span", {}, [document.createTextNode("Repo: "), strong(repo.owner ? `${repo.owner}/${repo.name}` : repo.name)]),
    el("span", {}, [document.createTextNode("Branch: "), strong(repo.branch || "n/a")]),
    el("span", {}, [document.createTextNode("Commit: "), strong(repo.commit_sha ? repo.commit_sha.slice(0, 7) : "n/a")]),
    el("span", {}, [document.createTextNode("URL: "), strong(repo.url || "local")]),
  ]);

  const summary = el("p", {
    className: "overview-summary",
    text: `This repo has ${pluralize(totalFiles, "file")} across ${pluralize(languages.length, "language")}, dominated by ${topLanguage}.`,
  });

  const langList = el(
    "ul",
    { className: "lang-list" },
    languages.map(([lang, count]) =>
      el("li", { className: "lang-chip" }, [strong(lang + ": "), document.createTextNode(pluralize(count, "file"))])
    )
  );

  return [meta, summary, langList];
}

function strong(text) {
  return el("strong", { text });
}

function renderStack(manifests) {
  if (!manifests.length) return [emptyNote("No manifest files detected.")];
  return manifests.map(renderManifest);
}

function renderManifest(manifest) {
  const title = el("p", { className: "manifest-title" }, [
    codeChip(manifest.path),
    document.createTextNode(" "),
    el("span", { className: "kind", text: `(${manifest.kind})` }),
    manifest.name ? document.createTextNode(` — ${manifest.name}`) : null,
  ]);

  const rows = [];
  if (manifest.dependencies.length) {
    const shown = manifest.dependencies.slice(0, 10).join(", ");
    const remainder = manifest.dependencies.length - 10;
    rows.push(
      el("p", {
        className: "manifest-row",
        text: `Dependencies: ${shown}${remainder > 0 ? `, +${remainder} more` : ""}`,
      })
    );
  }
  const scriptNames = Object.keys(manifest.scripts || {});
  if (scriptNames.length) {
    rows.push(el("p", { className: "manifest-row", text: `Scripts: ${scriptNames.join(", ")}` }));
  }
  if (!manifest.dependencies.length && !scriptNames.length) {
    rows.push(el("p", { className: "manifest-row", text: "No dependencies or scripts extracted." }));
  }

  return el("div", { className: "manifest-card" }, [title, ...rows]);
}

function renderEntrypoints(files) {
  const entrypoints = files.filter((f) => f.role === "entrypoint");
  if (!entrypoints.length) return [emptyNote("No entrypoints detected.")];
  return [
    el(
      "ul",
      { className: "entry-list" },
      entrypoints.map((f) => el("li", {}, [codeChip(f.path)]))
    ),
  ];
}

function renderFindings(findings) {
  return FINDING_CATEGORIES.map(([category, heading]) => {
    const matching = findings.filter((f) => f.category === category);
    return el("div", { className: "findings-category" }, [
      el("h3", { className: "section-subheading", text: heading }),
      ...(matching.length ? matching.map(renderFinding) : [emptyNote("No findings in this category.")]),
    ]);
  });
}

function renderFinding(finding) {
  const icon = SEVERITY_ICON[finding.severity] || "■";
  const head = el("div", { className: "finding-head" }, [
    el("span", {
      className: "severity-badge",
      attrs: { "data-severity": finding.severity },
      text: `${icon} ${finding.severity}`,
    }),
    el("span", { className: "confidence-badge", text: `confidence: ${finding.confidence}` }),
  ]);

  const evidenceRow = el("p", { className: "finding-line" }, [
    strong("Evidence"),
    ...finding.evidence.flatMap((path, i) => (i === 0 ? [codeChip(path)] : [document.createTextNode(", "), codeChip(path)])),
  ]);

  return el("div", { className: "finding-card", attrs: { "data-severity": finding.severity } }, [
    head,
    el("p", { className: "finding-title", text: finding.title }),
    evidenceRow,
    el("p", { className: "finding-line" }, [strong("Why it matters"), document.createTextNode(finding.explanation)]),
    el("p", { className: "finding-line" }, [strong("Recommendation"), document.createTextNode(finding.recommendation)]),
  ]);
}

function renderStartHere(modules) {
  if (!modules.length) return [emptyNote("No modules detected.")];
  const intro = el("p", {
    className: "empty-note",
    text: "Modules below are ordered by suggested read order: entrypoint first, then manifest/config, then everything else.",
  });
  return [intro, ...modules.map(renderModule)];
}

function renderModule(module) {
  const { fact, inference } = splitFactFromInference(module.description);
  const claims = [
    el("div", { className: "module-claim is-fact" }, [
      el("span", { className: "claim-label", text: "Fact" }),
      el("p", { text: fact }),
    ]),
  ];
  if (inference) {
    claims.push(
      el("div", { className: "module-claim is-inference" }, [
        el("span", { className: "claim-label", text: "Inference" }),
        el("p", { text: inference }),
      ])
    );
  }

  const keyFiles = module.key_files.length
    ? el("p", { className: "module-keyfiles" }, [
        strong("Key files: "),
        ...module.key_files.flatMap((path, i) => (i === 0 ? [codeChip(path)] : [document.createTextNode(", "), codeChip(path)])),
      ])
    : null;

  return el("div", { className: "module-card" }, [
    el("p", { className: "module-name", text: module.name }),
    ...claims,
    keyFiles,
  ]);
}

// Module descriptions are always exactly two sentences: a fact sentence
// (file count/language/key file) followed by a space and an inference
// sentence (see analyze.py's `_describe_module`). Split on the first
// ". " boundary rather than re-deriving the two claims from `files`, so
// this stays a display concern instead of duplicating analysis logic.
function splitFactFromInference(description) {
  const idx = description.indexOf(". ");
  if (idx === -1) return { fact: description, inference: "" };
  return { fact: description.slice(0, idx + 1), inference: description.slice(idx + 2) };
}

function emptyNote(text) {
  return el("p", { className: "empty-note", text });
}
