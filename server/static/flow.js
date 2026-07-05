// Blueprint — Slice 7 flow explorer controller. Owns only flow *selection*
// (the dropdown) and the plain-English explanation panel next to the
// diagram; all diagram drawing/layout is delegated to graph.js's
// `window.BlueprintFlowGraph` instance (a second `createGraphView` bound to
// its own SVG/drawer/toolbar) — this file never builds SVG elements itself,
// per the brief to reuse the existing renderer rather than build a second
// one. IIFE-wrapped, same convention as graph.js, so this file's small DOM
// helper doesn't leak into/collide with app.js's own `el`.
(function () {
  const flowView = document.getElementById("flow-view");
  const emptyNote = document.getElementById("flow-view-empty-note");
  const picker = document.getElementById("flow-picker");
  const select = document.getElementById("flow-select");
  const explanation = document.getElementById("flow-explanation");
  const diagramWrap = document.getElementById("flow-diagram-wrap");

  if (!flowView) return; // flow markup not present (shouldn't happen, defensive)

  let flows = [];

  select.addEventListener("change", () => showFlow(Number(select.value)));

  function render(index) {
    flows = index.flows || [];
    select.replaceChildren(
      ...flows.map((flow, i) => {
        const opt = document.createElement("option");
        opt.value = String(i);
        opt.textContent = flow.title;
        return opt;
      })
    );

    const hasFlows = flows.length > 0;
    emptyNote.hidden = hasFlows;
    picker.hidden = !hasFlows;
    diagramWrap.hidden = !hasFlows;
    explanation.replaceChildren();

    if (hasFlows) {
      select.selectedIndex = 0;
      showFlow(0);
    } else if (window.BlueprintFlowGraph) {
      window.BlueprintFlowGraph.render({ nodes: [], edges: [] });
    }
  }

  function showFlow(i) {
    const flow = flows[i];
    if (!flow) return;
    renderExplanation(flow);
    if (window.BlueprintFlowGraph) {
      window.BlueprintFlowGraph.render({ nodes: flow.nodes, edges: flow.edges });
    }
  }

  function renderExplanation(flow) {
    explanation.replaceChildren(
      el("h3", "flow-title", flow.title),
      el("p", "flow-explanation-text", flow.explanation),
      metaRow(flow)
    );
  }

  function metaRow(flow) {
    const row = document.createElement("p");
    row.className = "flow-meta";
    row.append(
      el("span", "confidence-badge", `confidence: ${flow.confidence}`),
      el("span", "flow-evidence-count", `${flow.evidence.length} file(s) of evidence`)
    );
    return row;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
  }

  // `render` may run while this tab is still hidden (zero-size SVG makes
  // the diagram's own fit-to-view a no-op) — app.js re-fits via
  // `window.BlueprintFlowGraph.fit()` once the "Flow Explorer" tab is
  // actually switched to, same pattern as the full graph view.
  window.BlueprintFlowView = { render };
})();
