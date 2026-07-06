// Blueprint — Slice 8 export wiring: "Copy Markdown" / "Download HTML" for
// the whole report, and "Copy Mermaid" on the Architecture Graph tab (full
// graph) and the Flow Explorer tab (currently selected flow). None of the
// rendering happens here — every button posts the already-fetched
// `RepoIndex` JSON (captured via `setAnalysis`, called from app.js right
// after a successful POST /api/analyze) to a small server endpoint that
// calls analyzer/mermaid.py, report.py's render_markdown, or
// analyzer/html_export.py directly, so nothing is duplicated in JS.
// IIFE-wrapped, same convention as graph.js/flow.js.
(function () {
  const exportBar = document.getElementById("export-bar");
  const copyMarkdownBtn = document.getElementById("export-copy-markdown");
  const downloadHtmlBtn = document.getElementById("export-download-html");
  const exportStatus = document.getElementById("export-status");
  const graphCopyMermaidBtn = document.getElementById("graph-copy-mermaid");
  const flowCopyMermaidBtn = document.getElementById("flow-copy-mermaid");
  const flowSelect = document.getElementById("flow-select");

  let lastAnalysis = null;
  let statusTimer = null;

  function setAnalysis(index) {
    lastAnalysis = index;
    if (exportBar) exportBar.hidden = false;
  }

  function hide() {
    lastAnalysis = null;
    if (exportBar) exportBar.hidden = true;
  }

  if (copyMarkdownBtn) {
    copyMarkdownBtn.addEventListener("click", () => {
      exportAndCopy("/api/export/markdown", { index: lastAnalysis }, copyMarkdownBtn);
    });
  }

  if (graphCopyMermaidBtn) {
    graphCopyMermaidBtn.addEventListener("click", () => {
      exportAndCopy(
        "/api/export/mermaid", { index: lastAnalysis, flow_index: null }, graphCopyMermaidBtn
      );
    });
  }

  if (flowCopyMermaidBtn) {
    flowCopyMermaidBtn.addEventListener("click", () => {
      const flowIndex = flowSelect && flowSelect.value !== "" ? Number(flowSelect.value) : null;
      if (flowIndex === null) {
        showStatus("Select a flow first.", true);
        return;
      }
      exportAndCopy(
        "/api/export/mermaid", { index: lastAnalysis, flow_index: flowIndex }, flowCopyMermaidBtn
      );
    });
  }

  if (downloadHtmlBtn) downloadHtmlBtn.addEventListener("click", downloadHtml);

  async function exportAndCopy(url, body, triggerBtn) {
    if (!lastAnalysis) return;
    triggerBtn.disabled = true;
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await response.text();
      if (!response.ok) {
        showStatus(`Export failed (HTTP ${response.status}).`, true);
        return;
      }
      await copyToClipboard(text);
    } catch (err) {
      showStatus("Could not reach the export endpoint.", true);
    } finally {
      triggerBtn.disabled = false;
    }
  }

  async function downloadHtml() {
    if (!lastAnalysis) return;
    downloadHtmlBtn.disabled = true;
    try {
      const response = await fetch("/api/export/html", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index: lastAnalysis }),
      });
      if (!response.ok) {
        showStatus(`Download failed (HTTP ${response.status}).`, true);
        return;
      }
      const html = await response.text();
      triggerDownload(html, `${safeFilenamePart(lastAnalysis.repo.name)}-blueprint-report.html`);
      showStatus("Downloaded.", false);
    } catch (err) {
      showStatus("Could not reach the export endpoint.", true);
    } finally {
      downloadHtmlBtn.disabled = false;
    }
  }

  function triggerDownload(content, filename) {
    const blob = new Blob([content], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function safeFilenamePart(value) {
    return (value || "repo").replace(/[^A-Za-z0-9._-]+/g, "_");
  }

  // ---------- Clipboard, with a manual fallback ----------
  //
  // navigator.clipboard.writeText requires a secure context + (in some
  // browsers/automation contexts) an explicit clipboard-write permission
  // grant. When it's unavailable or rejects, fall back to a selectable
  // <textarea> instead of failing silently.

  async function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        showStatus("Copied to clipboard.", false);
        return;
      } catch (err) {
        // fall through to the manual textarea fallback below
      }
    }
    showFallbackTextarea(text);
  }

  function showFallbackTextarea(text) {
    const existing = document.getElementById("export-fallback");
    if (existing) existing.remove();

    const wrap = document.createElement("div");
    wrap.id = "export-fallback";
    wrap.className = "export-fallback";

    const note = document.createElement("p");
    note.className = "export-fallback-note";
    note.textContent = "Clipboard access isn't available here — select the text below and copy manually.";

    const textarea = document.createElement("textarea");
    textarea.className = "export-fallback-textarea";
    textarea.readOnly = true;
    textarea.value = text;

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "export-button";
    closeBtn.textContent = "Close";
    closeBtn.addEventListener("click", () => wrap.remove());

    wrap.append(note, textarea, closeBtn);
    document.body.appendChild(wrap);
    textarea.focus();
    textarea.select();
  }

  function showStatus(message, isError) {
    if (!exportStatus) return;
    exportStatus.textContent = message;
    exportStatus.classList.toggle("is-error", !!isError);
    if (statusTimer) clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
      if (exportStatus.textContent === message) exportStatus.textContent = "";
    }, 4000);
  }

  window.BlueprintExport = { setAnalysis, hide };
})();
