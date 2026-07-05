// Blueprint — Slice 6 architecture graph view. Vanilla JS + SVG, no
// framework/build step (same decision as Slice 5's app.js — see
// docs/HANDOFF.md). Layout is computed by `dagre` (vendored at
// /vendor/dagre.min.js, layout-math only, no DOM rendering of its own) and
// then drawn as plain SVG <rect>/<path>/<text> elements we fully control.
//
// Everything here is wrapped in an IIFE so this file's helpers never leak
// into the shared global scope (app.js also declares small DOM helpers of
// its own; keeping this self-contained avoids an implicit load-order
// dependency between the two files). The only thing exposed globally is
// `window.BlueprintGraph.render(index)`, called by app.js once an analysis
// succeeds.
(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";

  const MIN_SCALE = 0.15;
  const MAX_SCALE = 3;
  const MIN_NODE_WIDTH = 90;
  const MAX_NODE_WIDTH = 260;
  const NODE_HEIGHT = 46;
  const NODE_PADDING_X = 16;
  const LABEL_FONT = "600 13px 'IBM Plex Mono', monospace";
  const TYPE_FONT = "700 9px 'IBM Plex Mono', monospace";
  const EDGE_LABEL_FONT = "600 10px 'IBM Plex Mono', monospace";
  const MAX_DRAWER_PATHS = 12;

  const svg = document.getElementById("graph-svg");
  const drawer = document.getElementById("graph-drawer");
  const filtersEl = document.getElementById("graph-filters");
  const searchInput = document.getElementById("graph-search");
  const emptyNote = document.getElementById("graph-empty-note");
  const zoomInBtn = document.getElementById("graph-zoom-in");
  const zoomOutBtn = document.getElementById("graph-zoom-out");
  const fitBtn = document.getElementById("graph-zoom-fit");

  if (!svg) return; // graph markup not present (shouldn't happen, defensive)

  svg.appendChild(svgEl("defs", {}, [buildArrowMarker()]));
  const edgesLayer = svgEl("g", { class: "graph-edges" });
  const nodesLayer = svgEl("g", { class: "graph-nodes" });
  const viewport = svgEl("g", { class: "graph-viewport" }, [edgesLayer, nodesLayer]);
  svg.appendChild(viewport);

  const state = {
    nodes: [], edges: [], hiddenTypes: new Set(),
    scale: 1, tx: 0, ty: 0,
  };
  let lastLayout = null; // the dagre graph instance from the last draw, for fit-to-view
  let dragState = null;
  let measureCtx = null;

  // ---------- Public entry point ----------

  function render(index) {
    state.nodes = index.nodes || [];
    state.edges = index.edges || [];
    state.hiddenTypes = new Set();
    searchInput.value = "";
    closeDrawer();
    buildFilterChips();

    if (!state.nodes.length) {
      emptyNote.hidden = false;
      clearLayer(edgesLayer);
      clearLayer(nodesLayer);
      return;
    }
    emptyNote.hidden = true;
    layoutAndDraw();
    fitToView();
  }

  // `render` runs right after an analysis completes, while the graph tab
  // (and its SVG) can still be `hidden` — `fitToView` is a no-op against a
  // zero-size container then. app.js calls `fit` again once the tab is
  // actually switched to and the SVG has real dimensions.
  window.BlueprintGraph = { render, fit: fitToView };

  // ---------- Layout + drawing ----------

  function layoutAndDraw() {
    const visibleNodes = state.nodes.filter((n) => !state.hiddenTypes.has(n.type));
    const visibleIds = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = state.edges.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target)
    );

    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", nodesep: 44, ranksep: 120, edgesep: 24, marginx: 24, marginy: 24 });
    g.setDefaultEdgeLabel(() => ({}));

    for (const node of visibleNodes) {
      const { width, height } = measureNodeBox(node);
      g.setNode(node.id, { width, height });
    }
    // No `name` argument: (source, target) pairs are always unique here —
    // a module-node id is always prefixed "module:" and a manifest-node id
    // "manifest:", so an "imports" edge and a "depends_on" edge can never
    // collide on the same (v, w) pair. Plain graphlib (not a multigraph)
    // is enough, and passing a name would throw ("isMultigraph = false").
    for (const edge of visibleEdges) {
      const { width, height } = measureEdgeLabel(edge.label);
      g.setEdge(edge.source, edge.target, { label: edge.label, width, height });
    }

    dagre.layout(g);
    lastLayout = g;
    drawGraph(g, visibleNodes, visibleEdges);
  }

  function drawGraph(g, visibleNodes, visibleEdges) {
    clearLayer(edgesLayer);
    clearLayer(nodesLayer);

    const nodesById = new Map(visibleNodes.map((n) => [n.id, n]));
    for (const edge of visibleEdges) {
      edgesLayer.appendChild(buildEdgeGroup(g.edge(edge.source, edge.target), edge));
    }
    for (const node of visibleNodes) {
      nodesLayer.appendChild(buildNodeGroup(g.node(node.id), nodesById.get(node.id)));
    }
    applySearchHighlight();
  }

  function clearLayer(layer) {
    while (layer.firstChild) layer.removeChild(layer.firstChild);
  }

  // ---------- Node + edge element construction ----------

  function buildNodeGroup(layout, node) {
    const { x, y, width, height } = layout;
    const innerWidth = width - NODE_PADDING_X * 2;
    const el = svgEl("g", {
      class: "graph-node", "data-id": node.id, "data-type": node.type, "data-label": node.label,
      transform: `translate(${x},${y})`,
    });
    el.appendChild(svgEl("rect", {
      class: "graph-node-rect", "data-type": node.type,
      x: -width / 2, y: -height / 2, width, height, rx: 6, ry: 6,
    }));
    el.appendChild(textEl(
      "graph-node-type", 0, -height / 2 + 15, truncateToWidth(node.type.toUpperCase(), TYPE_FONT, innerWidth)
    ));
    el.appendChild(textEl(
      "graph-node-label", 0, height / 2 - 12, truncateToWidth(node.label, LABEL_FONT, innerWidth)
    ));
    return el;
  }

  function buildEdgeGroup(layout, edge) {
    const group = svgEl("g", { class: "graph-edge-group" });
    const d = layout.points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
    group.appendChild(svgEl("path", {
      class: "graph-edge", "data-type": edge.type, d, "marker-end": "url(#graph-arrow)",
    }));
    if (layout.width && layout.height) {
      group.appendChild(svgEl("rect", {
        class: "graph-edge-label-bg",
        x: layout.x - layout.width / 2, y: layout.y - layout.height / 2,
        width: layout.width, height: layout.height, rx: 3, ry: 3,
      }));
      group.appendChild(textEl("graph-edge-label", layout.x, layout.y + 3, edge.label));
    }
    return group;
  }

  function buildArrowMarker() {
    const marker = svgEl("marker", {
      id: "graph-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5,
      markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse",
    });
    marker.appendChild(svgEl("path", { d: "M0,0 L10,5 L0,10 z", class: "graph-arrow-head" }));
    return marker;
  }

  function textEl(className, x, y, content) {
    const t = svgEl("text", { class: className, x, y, "text-anchor": "middle" });
    t.textContent = content;
    return t;
  }

  function svgEl(tag, attrs, children) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
    for (const child of children || []) node.appendChild(child);
    return node;
  }

  // ---------- Text measurement + truncation (keeps labels inside their box,
  // so long labels can never visually spill into a neighboring node/edge) ----------

  function measureTextWidth(text, font) {
    if (!measureCtx) measureCtx = document.createElement("canvas").getContext("2d");
    measureCtx.font = font;
    return measureCtx.measureText(text).width;
  }

  function measureNodeBox(node) {
    const labelWidth = measureTextWidth(node.label, LABEL_FONT);
    const typeWidth = measureTextWidth(node.type.toUpperCase(), TYPE_FONT);
    const width = clamp(Math.max(labelWidth, typeWidth) + NODE_PADDING_X * 2, MIN_NODE_WIDTH, MAX_NODE_WIDTH);
    return { width, height: NODE_HEIGHT };
  }

  function measureEdgeLabel(label) {
    return { width: measureTextWidth(label, EDGE_LABEL_FONT) + 14, height: 18 };
  }

  function truncateToWidth(text, font, maxWidth) {
    if (measureTextWidth(text, font) <= maxWidth) return text;
    let lo = 0;
    let hi = text.length;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      const candidate = `${text.slice(0, mid)}…`;
      if (measureTextWidth(candidate, font) <= maxWidth) lo = mid;
      else hi = mid - 1;
    }
    return lo === 0 ? "…" : `${text.slice(0, lo)}…`;
  }

  function clamp(value, lo, hi) {
    return Math.min(hi, Math.max(lo, value));
  }

  // ---------- Filter chips ----------

  function buildFilterChips() {
    const counts = new Map();
    for (const node of state.nodes) counts.set(node.type, (counts.get(node.type) || 0) + 1);
    const chips = [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([type, count]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "filter-chip is-active";
      btn.dataset.type = type;
      btn.textContent = `${type} (${count})`;
      btn.addEventListener("click", () => toggleTypeFilter(type, btn));
      return btn;
    });
    filtersEl.replaceChildren(...chips);
  }

  function toggleTypeFilter(type, btn) {
    if (state.hiddenTypes.has(type)) {
      state.hiddenTypes.delete(type);
      btn.classList.add("is-active");
    } else {
      state.hiddenTypes.add(type);
      btn.classList.remove("is-active");
    }
    layoutAndDraw();
    fitToView();
  }

  // ---------- Search ----------

  searchInput.addEventListener("input", applySearchHighlight);

  function applySearchHighlight() {
    const term = searchInput.value.trim().toLowerCase();
    nodesLayer.querySelectorAll(".graph-node").forEach((el) => {
      const label = (el.dataset.label || "").toLowerCase();
      const isMatch = term.length > 0 && label.includes(term);
      el.classList.toggle("is-match", isMatch);
      el.classList.toggle("is-dimmed", term.length > 0 && !isMatch);
    });
  }

  // ---------- Pan + zoom (a uniform transform on `viewport`, so anything
  // that doesn't overlap at scale 1 can't start overlapping at any other
  // zoom level) ----------

  function applyTransform() {
    viewport.setAttribute("transform", `translate(${state.tx},${state.ty}) scale(${state.scale})`);
  }

  function zoomAt(px, py, factor) {
    const newScale = clamp(state.scale * factor, MIN_SCALE, MAX_SCALE);
    const ratio = newScale / state.scale;
    state.tx = px - ratio * (px - state.tx);
    state.ty = py - ratio * (py - state.ty);
    state.scale = newScale;
    applyTransform();
  }

  function fitToView() {
    if (!lastLayout) return;
    const bbox = computeBBox(lastLayout);
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height || !bbox.width || !bbox.height) return;
    // Deliberately not clamped to MIN_SCALE/MAX_SCALE (those bound manual
    // wheel/button zoom only): "fit" means the whole graph must end up
    // visible, even a sparse one that would otherwise need a scale outside
    // that manual range. Clamping here previously left nodes clipped
    // outside the canvas for small/disconnected graphs.
    const scale = Math.min((rect.width - 60) / bbox.width, (rect.height - 60) / bbox.height);
    state.scale = scale;
    state.tx = rect.width / 2 - (bbox.minX + bbox.width / 2) * scale;
    state.ty = rect.height / 2 - (bbox.minY + bbox.height / 2) * scale;
    applyTransform();
  }

  function computeBBox(g) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const id of g.nodes()) {
      const n = g.node(id);
      minX = Math.min(minX, n.x - n.width / 2);
      minY = Math.min(minY, n.y - n.height / 2);
      maxX = Math.max(maxX, n.x + n.width / 2);
      maxY = Math.max(maxY, n.y + n.height / 2);
    }
    if (!isFinite(minX)) return { minX: 0, minY: 0, width: 0, height: 0 };
    return { minX, minY, width: maxX - minX, height: maxY - minY };
  }

  zoomInBtn.addEventListener("click", () => {
    const rect = svg.getBoundingClientRect();
    zoomAt(rect.width / 2, rect.height / 2, 1.25);
  });
  zoomOutBtn.addEventListener("click", () => {
    const rect = svg.getBoundingClientRect();
    zoomAt(rect.width / 2, rect.height / 2, 0.8);
  });
  fitBtn.addEventListener("click", fitToView);

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = svg.getBoundingClientRect();
    const factor = Math.exp(-event.deltaY * 0.001);
    zoomAt(event.clientX - rect.left, event.clientY - rect.top, factor);
  }, { passive: false });

  svg.addEventListener("pointerdown", (event) => {
    const nodeEl = event.target.closest && event.target.closest(".graph-node");
    dragState = {
      startX: event.clientX, startY: event.clientY, tx0: state.tx, ty0: state.ty,
      moved: false, nodeId: nodeEl ? nodeEl.dataset.id : null,
    };
    svg.setPointerCapture(event.pointerId);
  });

  svg.addEventListener("pointermove", (event) => {
    if (!dragState) return;
    const dx = event.clientX - dragState.startX;
    const dy = event.clientY - dragState.startY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragState.moved = true;
    if (dragState.moved) {
      state.tx = dragState.tx0 + dx;
      state.ty = dragState.ty0 + dy;
      applyTransform();
    }
  });

  svg.addEventListener("pointerup", () => {
    if (dragState && !dragState.moved) {
      if (dragState.nodeId) {
        const node = state.nodes.find((n) => n.id === dragState.nodeId);
        if (node) openDrawer(node);
      } else {
        closeDrawer();
      }
    }
    dragState = null;
  });

  // ---------- Node drawer ----------

  function openDrawer(node) {
    drawer.hidden = false;
    drawer.replaceChildren(
      drawerCloseButton(),
      drawerText("drawer-type", node.type),
      drawerText("drawer-label", node.label, "h3"),
      drawerRow("Files", node.file_paths),
      drawerRow("Evidence", node.evidence),
      drawerConfidence(node.confidence)
    );
  }

  function closeDrawer() {
    drawer.hidden = true;
    drawer.replaceChildren();
  }

  function drawerCloseButton() {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "drawer-close";
    btn.setAttribute("aria-label", "Close detail panel");
    btn.textContent = "×";
    btn.addEventListener("click", closeDrawer);
    return btn;
  }

  function drawerText(className, text, tag) {
    const node = document.createElement(tag || "p");
    node.className = className;
    node.textContent = text;
    return node;
  }

  function drawerRow(label, paths) {
    const shown = (paths || []).slice(0, MAX_DRAWER_PATHS);
    const remainder = (paths || []).length - shown.length;
    const row = document.createElement("div");
    row.className = "drawer-row";
    const labelEl = document.createElement("span");
    labelEl.className = "claim-label";
    labelEl.textContent = label;
    row.appendChild(labelEl);
    const chips = document.createElement("div");
    chips.className = "drawer-chips";
    for (const path of shown) {
      const chip = document.createElement("code");
      chip.className = "code-chip";
      chip.textContent = path;
      chips.appendChild(chip);
    }
    row.appendChild(chips);
    if (remainder > 0) {
      const more = document.createElement("span");
      more.className = "drawer-more";
      more.textContent = `+${remainder} more`;
      row.appendChild(more);
    }
    return row;
  }

  function drawerConfidence(confidence) {
    const p = document.createElement("p");
    p.className = "drawer-confidence";
    const label = document.createElement("span");
    label.className = "claim-label";
    label.textContent = "Confidence";
    p.append(label, document.createTextNode(` ${confidence}`));
    return p;
  }
})();
