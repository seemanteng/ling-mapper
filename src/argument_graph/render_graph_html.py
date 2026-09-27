"""Render argument_graph/0.1 files as a self-contained HTML viewer.

Left: the essay tiled into units, with relation signals marked. Right: the primary
tree (satellite -> nucleus) with relation labels, or the derived support/attack view.
Validation errors from `validate_graph` are shown, never hidden or repaired.
"""
import argparse
import html
import json
from pathlib import Path

from .graph_schema import RELATIONS, argument_edges, propositions, validate_graph


def graph_data(graph, record):
    text = record["response_text"]
    return {
        "id": record["example_id"], "score": record["metadata"].get("holistic_score"),
        "prompt": record["prompt"], "text": text, "root": graph.get("root"),
        "units": graph.get("units", []), "relations": graph.get("relations", []),
        "derived": argument_edges(graph), "errors": validate_graph(graph, text), "props": propositions(graph),
        "provenance": graph.get("provenance", {}), "schema": graph.get("schema_version"),
    }


def render(pairs, title="Argument graph"):
    data = [graph_data(g, r) for g, r in pairs]
    definitions = {k: {"nuclearity": v[0], "definition": v[1]} for k, v in RELATIONS.items()}
    payload = json.dumps({"essays": data, "relations": definitions}, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #fafaf8; --panel: #ffffff; --ink: #1d1d1f; --muted: #6b6b70; --line: #e3e3e0; --warn: #b3261e;
  --lead: #8a8a8a; --position: #0072b2; --claim: #3a9ad9; --counterclaim: #d55e00;
  --rebuttal: #cc79a7; --evidence: #009e73; --concluding_summary: #e69f00; --unannotated: #b8b8b8;
  --explanation: #009e73; --adversative: #d55e00; --causal: #a9559b; --structure: #8a8a8a; --framing: #0072b2;
  --support: #009e73; --attack: #d55e00;
  --tint: 13%; --tint-hl: 34%;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #161618; --panel: #1f1f22; --ink: #ececef; --muted: #9a9aa2; --line: #333338; --warn: #ff8a80;
          --tint: 22%; --tint-hl: 46%; color-scheme: dark; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--bg); border-bottom: 1px solid var(--line);
         padding: 10px 20px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
header h1 { font-size: 16px; margin: 0; font-weight: 600; }
select, button { font: inherit; font-size: 13px; color: inherit; background: var(--panel); border: 1px solid var(--line);
                 border-radius: 6px; padding: 4px 9px; cursor: pointer; }
button[aria-pressed="true"] { background: var(--ink); color: var(--panel); border-color: var(--ink); }
.meta { color: var(--muted); font-size: 13px; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line); }
.badge.ok { color: var(--explanation); border-color: var(--explanation); }
.badge.bad { color: var(--warn); border-color: var(--warn); }
.draft { font-size: 12px; color: var(--warn); }
main { display: grid; grid-template-columns: minmax(0, 0.85fr) minmax(0, 1.6fr); gap: 18px; padding: 18px 20px; }
@media (max-width: 1000px) { main { grid-template-columns: 1fr; } }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; min-width: 0; }
h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 10px; font-weight: 600; }
.pane { max-height: calc(100vh - 140px); overflow: auto; }
.prompt { color: var(--muted); font-size: 13px; margin: 0 0 12px; }
#essay { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.9; }
.unit { background: color-mix(in srgb, var(--c) var(--tint), transparent); border-bottom: 2px solid var(--c);
        border-radius: 3px; cursor: pointer; padding: 2px 0; }
.unit.hl { background: color-mix(in srgb, var(--c) var(--tint-hl), transparent); }
.unit.not-own { border-bottom-style: dashed; }
.uid { font-size: 10px; color: var(--muted); vertical-align: super; margin: 0 2px 0 1px; font-weight: 600; }
.sig { font-weight: 700; text-decoration: underline dotted; text-underline-offset: 3px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 10px; }
.toolbar .hint { margin-left: auto; font-size: 12px; color: var(--muted); }
#graph { height: calc(100vh - 330px); min-height: 380px; border: 1px solid var(--line); border-radius: 8px;
         cursor: grab; touch-action: none; overflow: hidden; }
#graph.dragging { cursor: grabbing; }
#graph svg { width: 100%; height: 100%; display: block; }
g.node { cursor: pointer; }
g.node rect { fill: color-mix(in srgb, var(--c) var(--tint), var(--panel)); stroke: var(--c); stroke-width: 1.5; }
g.node.not-own rect { stroke-dasharray: 5 3; }
g.node.hl rect, g.node.sel rect { fill: color-mix(in srgb, var(--c) var(--tint-hl), var(--panel)); stroke-width: 3; }
g.node .role { font: 700 10.5px sans-serif; letter-spacing: .05em; fill: var(--c); }
g.node .stance { font: 700 10px sans-serif; letter-spacing: .04em; fill: var(--warn); }
g.node .body { font: 12.5px sans-serif; fill: var(--ink); }
g.edge { cursor: pointer; }
g.edge path.line { fill: none; stroke: var(--c); stroke-width: 1.7; }
g.edge.implicit path.line { opacity: .55; }
g.edge.secondary path.line { stroke-dasharray: 7 4; }
g.edge path.halo { fill: none; stroke: #f5c400; stroke-width: 9; opacity: .45; }
g.edge path.hit { fill: none; stroke: transparent; stroke-width: 12; }
g.edge text { font: 600 10.5px sans-serif; fill: var(--c); paint-order: stroke; stroke: var(--panel); stroke-width: 4px; }
g.edge.implicit text { font-style: italic; }
g.edge.hl path.line, g.edge.sel path.line { stroke-width: 3.4; opacity: 1; }
#props { height: calc(100vh - 330px); min-height: 380px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; padding: 6px 12px; }
#props .prop { border-left: 3px solid var(--c); padding: 5px 0 5px 10px; margin: 6px 0; cursor: default; }
#props .prop.hl { background: color-mix(in srgb, var(--c) var(--tint), transparent); }
#props .ptag { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; font-weight: 600; color: var(--c); margin-right: 6px; }
#props .pout { font-size: 12px; color: var(--muted); margin-top: 2px; }
#details { margin-top: 10px; font-size: 13px; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; min-height: 58px; }
#details .k { color: var(--muted); }
#details q { font-style: italic; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--muted); margin-top: 10px; }
.legend span::before { content: ""; display: inline-block; width: 16px; height: 0; border-top: 3px solid var(--c);
                       margin-right: 5px; vertical-align: 3px; }
.legend span.dash::before { border-top-style: dashed; }
.legend span.faint::before { opacity: .5; }
g.panel rect { fill: color-mix(in srgb, var(--muted) 6%, transparent); stroke: var(--line); stroke-width: 1.2; }
g.panel { cursor: pointer; }
g.panel .ptitle { font: 800 13px sans-serif; letter-spacing: .06em; fill: var(--ink); }
g.panel .phead { font: 600 13px sans-serif; letter-spacing: 0; fill: var(--ink); }
g.panel .phow { font: 500 12px sans-serif; letter-spacing: 0; fill: var(--muted); }
.chip { display: inline-block; font: 700 10.5px sans-serif; letter-spacing: .05em; text-transform: uppercase; padding: 1px 7px;
        margin: 0 6px 0 0; border-radius: 999px; background: var(--ink); color: var(--panel); border: 0; vertical-align: 2px; }
#errors { color: var(--warn); font-size: 13px; margin: 0 0 10px; padding-left: 18px; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <select id="pick" aria-label="Essay"></select>
  <span class="meta" id="meta"></span>
  <span class="badge" id="valid"></span>
  <span class="draft" id="draft"></span>
</header>
<main>
  <section><h2>Essay, tiled into units</h2><div class="pane">
    <p class="prompt" id="prompt"></p><div id="essay"></div>
    <p class="legend"><span style="--c: var(--muted)">unit (colour = role)</span><span class="dash" style="--c: var(--muted)">dashed = conceded / rejected / reported</span><span style="--c: transparent"><b class="sig">bold</b>&nbsp;= relation signal</span></p>
  </div></section>
  <section><h2>Argument graph</h2>
    <ul id="errors" hidden></ul>
    <div class="toolbar">
      <button id="v-rel" aria-pressed="true">Relations</button><button id="v-arg" aria-pressed="false">Support / attack</button><button id="v-prop" aria-pressed="false" title="Units joined with their frames, conditions and split parts">Propositions</button>
      <button id="fit">Fit width</button><button id="all">Whole graph</button>
      <span class="hint">Scroll to pan · pinch or ⌘/Ctrl-scroll to zoom · click a node or edge for details</span>
    </div>
    <div id="graph"></div>
    <div id="props" hidden></div>
    <div id="details"><span class="k">Click a node or an edge.</span></div>
    <div class="legend" id="legend"></div>
  </section>
</main>
<script>
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const W = 230, H = 88, VGAP = 14, HGAP = 90;
const CLASS = l => l.startsWith("explanation") ? "explanation" : l.startsWith("adversative") ? "adversative"
  : (l.startsWith("causal") || l.startsWith("contingency")) ? "causal"
  : (l.startsWith("elaboration") || l.startsWith("restatement") || l.startsWith("joint") || l.startsWith("mode") || l === "same-unit") ? "structure" : "framing";
const SHORT = l => l.replace(/^(explanation|adversative|causal|contingency|elaboration|restatement|attribution|evaluation|context|organization|joint|mode|topic)-/, "");
const ROLE = r => r.replace("_", " ").toUpperCase();
const NOT_OWN = new Set(["conceded", "rejected", "reported"]);
let cur = 0, mode = "rel", view = null, box = null, lastPos = null, lastGroups = [];

function mk(tag, attrs, text, svg) {
  const e = svg ? document.createElementNS(NS, tag) : document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => k === "c" ? e.style.setProperty("--c", v) : e.setAttribute(k, v));
  if (text !== undefined) e.textContent = text;
  return e;
}
const svg = (t, a, x) => mk(t, a, x, true);

function wrap(text, width = 33, lines = 3) {
  const words = text.split(/\s+/).filter(Boolean), out = [];
  let line = "";
  for (const w of words) {
    if ((line + " " + w).trim().length > width) { out.push(line); line = w; if (out.length === lines) break; }
    else line = (line + " " + w).trim();
  }
  if (out.length < lines && line) out.push(line);
  if (out.join(" ").split(/\s+/).length < words.length) out[out.length - 1] = out[out.length - 1].replace(/.{0,2}$/, "") + "…";
  return out;
}

function renderEssay(d) {
  const essay = $("essay"); essay.replaceChildren();
  const groups = layout(d).groups, chips = new Map(groups.map((g, i) => [g.first, i]));
  const sigs = d.relations.flatMap(r => (r.signals || []).map(s => ({...s, cls: CLASS(r.label), rel: r.id})));
  let pos = 0;
  for (const u of [...d.units].sort((a, b) => a.start - b.start)) {
    if (u.start > pos) essay.append(d.text.slice(pos, u.start));
    const span = mk("span", {class: "unit" + (NOT_OWN.has(u.stance) ? " not-own" : ""), "data-id": u.id, c: `var(--${u.role})`,
                             title: `${u.id} · ${ROLE(u.role)} · ${u.stance}`});
    let p = u.start;
    for (const s of sigs.filter(s => s.start >= u.start && s.end <= u.end).sort((a, b) => a.start - b.start)) {
      if (s.start < p) continue;
      span.append(d.text.slice(p, s.start));
      span.append(mk("b", {class: "sig", "data-rel": s.rel, c: `var(--${s.cls})`, style: `color: var(--${s.cls})`}, d.text.slice(s.start, s.end)));
      p = s.end;
    }
    span.append(d.text.slice(p, u.end));
    const gi = chips.get(u.id);
    if (gi !== undefined) { const g = groups[gi];
      essay.append(mk("button", {class: "chip", "data-group": gi, title: "Show in graph"}, g.title === "THESIS" || !g.title.startsWith("POINT") ? g.title.toLowerCase() : g.title.replace("POINT", "Point"))); }
    essay.append(mk("span", {class: "uid"}, u.id.replace("u", "")), span);
    pos = u.end;
  }
  essay.append(d.text.slice(pos));
  essay.querySelectorAll("b.sig").forEach(b => b.style.setProperty("color", b.style.getPropertyValue("--c")));
}

// Display grouping only (the graph itself is unchanged): each child of the root is placed
// in the panel of its paragraph, so the tree reads thesis -> point 1 (subtree) -> point 2 ...
const TITLE = 34, GROUP_GAP = 26, PANEL_PAD = 12;
function paragraphOf(text) {
  const breaks = [...text.matchAll(/\n\s*\n/g)].map(m => m.index);
  return pos => breaks.filter(b => b < pos).length;
}
function layout(d) {
  const kids = {}, head = {}, relOf = {};
  d.relations.filter(r => r.tier === "primary").forEach(r => { head[r.source] = r.target; relOf[r.source] = r; (kids[r.target] ||= []).push(r.source); });
  const unit = Object.fromEntries(d.units.map(u => [u.id, u]));
  Object.values(kids).forEach(k => k.sort((a, b) => unit[a].start - unit[b].start));
  const para = paragraphOf(d.text);
  const rootId = d.root && unit[d.root] ? d.root : (d.units.find(u => !head[u.id]) || d.units[0]).id;
  const byPara = new Map();
  // Key = paragraph, with concluding units split off, so a closing point and the conclusion get separate panels.
  const keyOf = id => para(unit[id].start) * 2 + (unit[id].role === "concluding_summary" ? 1 : 0);
  for (const c of kids[rootId] || []) { const k = keyOf(c); if (!byPara.has(k)) byPara.set(k, []); byPara.get(k).push(c); }
  const pos = {}, groups = [];
  let offset = TITLE, point = 0;
  const rootPara = para(unit[rootId].start) * 2;
  const place = (id, depth, seen, st) => {
    const ch = (kids[id] || []).filter(k => !seen.has(k) && !pos[k]);
    ch.forEach(k => place(k, depth + 1, new Set([...seen, k]), st));
    const ys = ch.map(k => pos[k] && pos[k].y).filter(y => y !== undefined);
    pos[id] = {x: depth * (W + HGAP), y: ys.length ? Math.min(...ys) : offset + st.slot++ * (H + VGAP)};
  };
  const members = id => [id, ...(kids[id] || []).flatMap(members)];
  const keys = [...byPara.keys()].sort((a, b) => a - b);
  if (!byPara.has(rootPara)) keys.unshift(rootPara);
  for (const k of keys) {
    const heads = byPara.get(k) || [], st = {slot: 0};
    if (k === rootPara) { pos[rootId] = {x: 0, y: offset}; st.slot = heads.length ? 0 : 1; }
    heads.forEach(h => place(h, 1, new Set([rootId, h]), st));
    const ids = heads.flatMap(members).concat(k === rootPara ? [rootId] : []);
    const ys = ids.map(i => pos[i].y), xs = ids.map(i => pos[i].x);
    const rels = heads.map(h => relOf[h]).filter(Boolean);
    const heading = ids.map(i => unit[i]).filter(u => relOf[u.id] && relOf[u.id].label === "organization-preparation")
                       .sort((a, b) => a.start - b.start)[0];
    let title;
    if (k === rootPara) title = "THESIS";
    else if (ids.some(i => unit[i].role === "concluding_summary")) title = "CONCLUSION";
    else if (rels.some(r => r.label.startsWith("explanation"))) title = `POINT ${++point}`;
    else if (rels.every(r => r.label === "context-background")) title = "BACKGROUND";
    else title = "NOT LINKED AS A REASON";
    const how = [...new Set(rels.map(r => SHORT(r.label)))].join(", ");
    groups.push({title, heading: heading ? heading.text.trim().replace(/:$/, "") : "", how,
                 first: ids.map(i => unit[i]).sort((a, b) => a.start - b.start)[0].id,
                 x: Math.min(...xs) - PANEL_PAD, y: Math.min(...ys) - TITLE,
                 w: Math.max(...xs) - Math.min(...xs) + W + 2 * PANEL_PAD, h: Math.max(...ys) - Math.min(...ys) + H + TITLE + PANEL_PAD});
    offset = Math.max(...ys) + H + GROUP_GAP + TITLE;
  }
  // Anything not reachable from the root (should not happen in a valid graph) goes last.
  const rest = d.units.filter(u => !pos[u.id]);
  if (rest.length) {
    const st = {slot: 0};
    rest.forEach(u => { if (!pos[u.id]) place(u.id, 1, new Set([u.id]), st); });
    const ys = rest.map(u => pos[u.id].y), xs = rest.map(u => pos[u.id].x);
    groups.push({title: "UNATTACHED", heading: "", how: "", first: rest[0].id, x: Math.min(...xs) - PANEL_PAD, y: Math.min(...ys) - TITLE,
                 w: Math.max(...xs) - Math.min(...xs) + W + 2 * PANEL_PAD, h: Math.max(...ys) - Math.min(...ys) + H + TITLE + PANEL_PAD});
  }
  return {pos, groups};
}

function curve(a, b) {  // from satellite a (right) to nucleus b (left)
  const x1 = a.x, y1 = a.y + H / 2, x2 = b.x + W, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
  return {d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, lx: mx, ly: (y1 + y2) / 2, sx: x1 - 6, sy: y1 - 5};
}

function drawGraph(d) {
  const {pos, groups} = layout(d); lastPos = pos; lastGroups = groups;
  const root = svg("svg", {preserveAspectRatio: "xMinYMin meet", role: "img", "aria-label": "Argument graph"});
  const defs = svg("defs");
  ["explanation", "adversative", "causal", "structure", "framing", "support", "attack"].forEach(c => {
    const m = svg("marker", {id: `ar-${c}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse"});
    m.append(svg("path", {d: "M0,0 L10,5 L0,10 z", fill: `var(--${c})`})); defs.append(m);
  });
  root.append(defs);
  const pG = svg("g"), eG = svg("g"), nG = svg("g");
  groups.forEach((g, i) => {
    const panel = svg("g", {class: "panel", "data-group": i});
    panel.append(svg("rect", {x: g.x, y: g.y, width: g.w, height: g.h, rx: 12}));
    const t = svg("text", {class: "ptitle", x: g.x + 14, y: g.y + 22}, g.title);
    if (g.heading) t.append(svg("tspan", {class: "phead"}, `  ·  ${g.heading}`));
    if (g.how && g.title !== "THESIS") t.append(svg("tspan", {class: "phow"}, `   (${g.how} → thesis)`));
    panel.append(t); pG.append(panel);
  });
  if (mode === "rel") {
    for (const r of d.relations) {
      if (!pos[r.source] || !pos[r.target]) continue;
      const c = CLASS(r.label), k = curve(pos[r.source], pos[r.target]);
      const pending = (d.provenance.pending_review || []).includes(r.id);
      const g = svg("g", {class: `edge ${r.tier}` + (r.implicit ? " implicit" : "") + (pending ? " pending" : ""), "data-rel": r.id, "data-from": r.source, "data-to": r.target, c: `var(--${c})`});
      if (pending) g.append(svg("path", {class: "halo", d: k.d}));
      g.append(svg("path", {class: "hit", d: k.d}), svg("path", {class: "line", d: k.d, "marker-end": `url(#ar-${c})`}));
      g.append(svg("text", {x: k.sx, y: k.sy, "text-anchor": "end"}, SHORT(r.label) + (pending ? " ●" : "")));
      eG.append(g);
    }
  } else {
    // Derived view: faint primary skeleton, then support/attack arcs in their own direction.
    for (const r of d.relations.filter(r => r.tier === "primary")) {
      const k = curve(pos[r.source], pos[r.target]);
      eG.append(svg("path", {d: k.d, fill: "none", stroke: "var(--line)", "stroke-width": 1.2}));
    }
    d.derived.forEach((e, i) => {
      const a = pos[e.source], b = pos[e.target]; if (!a || !b) return;
      const rightToLeft = a.x >= b.x;
      const k = rightToLeft ? curve(a, b) : (() => { const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
        return {d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, lx: mx, ly: (y1 + y2) / 2}; })();
      const g = svg("g", {class: "edge", "data-rel": e.relation, "data-from": e.source, "data-to": e.target, c: `var(--${e.type})`});
      g.append(svg("path", {class: "hit", d: k.d}), svg("path", {class: "line", d: k.d, "marker-end": `url(#ar-${e.type})`}));
      g.append(svg("text", {x: k.lx, y: k.ly - 4, "text-anchor": "middle"}, e.type));
      eG.append(g);
    });
  }
  for (const u of d.units) {
    const p = pos[u.id], g = svg("g", {class: "node" + (NOT_OWN.has(u.stance) ? " not-own" : ""), "data-id": u.id,
                                       c: `var(--${u.role})`, transform: `translate(${p.x},${p.y})`});
    g.append(svg("title", {}, `${u.id} · ${ROLE(u.role)} · ${u.stance}\n${u.text}`));
    g.append(svg("rect", {width: W, height: H, rx: 8}));
    g.append(svg("text", {class: "role", x: 10, y: 17}, `${u.id.toUpperCase()}  ${ROLE(u.role)}` + (u.id === d.root ? "  · ROOT" : "")));
    if (u.stance !== "endorsed") g.append(svg("text", {class: "stance", x: W - 10, y: 17, "text-anchor": "end"}, u.stance.toUpperCase()));
    wrap(u.text.trim()).forEach((line, i) => g.append(svg("text", {class: "body", x: 10, y: 37 + i * 16}, line)));
    nG.append(g);
  }
  root.append(pG, eG, nG);
  $("graph").replaceChildren(root);
  const xs = Object.values(pos).map(p => p.x).concat(groups.map(g => g.x)),
        ys = Object.values(pos).map(p => p.y).concat(groups.map(g => g.y)), pad = 24;
  box = {x: Math.min(...xs) - pad, y: Math.min(...ys) - pad,
         w: Math.max(...xs) - Math.min(...xs) + W + 2 * pad, h: Math.max(...ys) - Math.min(...ys) + H + 2 * pad};
  fitWidth();
}
function setView(v) { view = v; $("graph").firstChild.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`); }
function fitWidth() { const r = $("graph").getBoundingClientRect(); const s = r.width / box.w;
  setView({x: box.x, y: box.y, w: box.w, h: r.height / s}); }
function fitAll() { setView({...box}); }

function details(html) { $("details").innerHTML = html; }
const esc = s => s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function showUnit(d, id) {
  const u = d.units.find(u => u.id === id); if (!u) return;
  const out = d.relations.filter(r => r.source === id), inc = d.relations.filter(r => r.target === id);
  details(`<b>${u.id}</b> · ${ROLE(u.role)} · <span class="k">stance</span> ${u.stance}${u.id === d.root ? " · <b>root</b>" : ""}<br><q>${esc(u.text)}</q><br>
    <span class="k">attaches to:</span> ${out.map(r => `${SHORT(r.label)} → ${r.target}`).join(", ") || "—"} ·
    <span class="k">children:</span> ${inc.length}`);
}
function showRel(d, rid) {
  const r = d.relations.find(r => r.id === rid); if (!r) return;
  const def = DATA.relations[r.label] || {};
  const sig = (r.signals || []).map(s => `<q>${esc(s.text)}</q> (${s.type})`).join(", ");
  const der = d.derived.filter(e => e.relation === rid).map(e => `${e.type}: ${e.source} → ${e.target}`).join(", ");
  details(`<b>${r.label}</b> · ${r.tier} · ${r.source} → ${r.target}<br><span class="k">Definition:</span> ${esc(def.definition || "")}<br>
    ${(d.provenance.pending_review || []).includes(rid) ? '<b style="color: var(--warn)">Changed — pending your review.</b><br>' : ""}<span class="k">Signal:</span> ${sig || "<i>implicit</i>"}${der ? ` · <span class="k">derived:</span> ${der}` : ""}${r.note ? `<br><span class="k">Note:</span> ${esc(r.note)}` : ""}`);
}

function hl(id, on) {
  document.querySelectorAll(`[data-id="${id}"], g.edge[data-from="${id}"], g.edge[data-to="${id}"]`).forEach(e => e.classList.toggle("hl", on));
}
document.addEventListener("mouseover", e => { const t = e.target.closest("[data-id]"); if (t) hl(t.dataset.id, true); });
document.addEventListener("mouseout", e => { const t = e.target.closest("[data-id]"); if (t) hl(t.dataset.id, false); });
document.addEventListener("click", e => {
  if ($("graph").dataset.dragged) { delete $("graph").dataset.dragged; return; }
  const d = DATA.essays[cur];
  const chip = e.target.closest("[data-group]");
  if (chip && !e.target.closest("[data-id]")) { const g = lastGroups[+chip.dataset.group];
    if (g && view) setView({...view, x: box.x, y: g.y - 12}); return; }
  const edge = e.target.closest("g.edge, b.sig"), node = e.target.closest("[data-id]");
  document.querySelectorAll(".sel").forEach(x => x.classList.remove("sel"));
  if (edge && edge.dataset.rel) {
    showRel(d, edge.dataset.rel);
    document.querySelectorAll(`g.edge[data-rel="${edge.dataset.rel}"]`).forEach(x => x.classList.add("sel"));
  } else if (node) {
    showUnit(d, node.dataset.id);
    document.querySelectorAll(`g.node[data-id="${node.dataset.id}"]`).forEach(x => x.classList.add("sel"));
    if (node.tagName !== "SPAN") document.querySelector(`span.unit[data-id="${node.dataset.id}"]`)?.scrollIntoView({behavior: "smooth", block: "center"});
    else centreOn(node.dataset.id);
  }
});
function centreOn(id) { const p = lastPos[id]; if (p && view) setView({...view, x: p.x + W / 2 - view.w / 2, y: p.y + H / 2 - view.h / 2}); }

(function panZoom() {
  const el = $("graph"); let drag = null;
  const scale = () => { const r = el.getBoundingClientRect(); return Math.max(view.w / r.width, view.h / r.height); };
  el.addEventListener("wheel", e => {
    if (!view) return; e.preventDefault();
    const s = scale();
    if (e.ctrlKey || e.metaKey) {
      const r = el.getBoundingClientRect(), k = Math.exp(e.deltaY * 0.01);
      const px = view.x + (e.clientX - r.left) * s, py = view.y + (e.clientY - r.top) * s;
      setView({x: px - (px - view.x) * k, y: py - (py - view.y) * k, w: view.w * k, h: view.h * k});
    } else setView({...view, x: view.x + e.deltaX * s, y: view.y + e.deltaY * s});
  }, {passive: false});
  el.addEventListener("pointerdown", e => { if (view) drag = {x: e.clientX, y: e.clientY, v: {...view}, s: scale(), moved: false}; });
  window.addEventListener("pointermove", e => {
    if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; el.classList.add("dragging"); }
    if (drag.moved) setView({...drag.v, x: drag.v.x - dx * drag.s, y: drag.v.y - dy * drag.s});
  });
  window.addEventListener("pointerup", () => { if (drag && drag.moved) el.dataset.dragged = "1"; drag = null; el.classList.remove("dragging"); });
})();

function legend() {
  const L = $("legend"); L.replaceChildren();
  const items = mode === "rel"
    ? [["explanation", "evidence / justify"], ["adversative", "concession / antithesis / contrast"], ["causal", "cause / result / condition"],
       ["structure", "elaboration / restatement / list"], ["framing", "attribution / background / preparation / question / solution"]]
    : [["support", "support (derived)"], ["attack", "attack (derived)"]];
  items.forEach(([c, t]) => L.append(mk("span", {c: `var(--${c})`}, t)));
  if (mode === "rel") { L.append(mk("span", {class: "faint", c: "var(--muted)"}, "faint + italic = implicit (no signal)"));
                        if (DATA.essays[cur].provenance.pending_review?.length) L.append(mk("span", {c: "#f5c400"}, "yellow halo ● = changed, pending review"));
                        L.append(mk("span", {class: "dash", c: "var(--muted)"}, "dashed = secondary edge")); }
}
function show(i) {
  cur = i; const d = DATA.essays[i];
  $("pick").value = i;
  $("meta").textContent = `score ${d.score ?? "–"} · ${d.units.length} units · ${d.relations.length} relations · ${d.derived.length} derived`;
  const ok = d.errors.length === 0;
  $("valid").textContent = ok ? `✓ valid ${d.schema}` : `✗ ${d.errors.length} contract violation${d.errors.length > 1 ? "s" : ""}`;
  $("valid").className = "badge " + (ok ? "ok" : "bad");
  const prov = d.provenance || {};
  const reviewed = prov.review_status === "human_reviewed";
  $("draft").textContent = prov.annotator || prov.review_status
    ? `annotated by ${prov.annotator || "unknown"} · ${reviewed ? `reviewed by ${prov.reviewer || "a human"}` +
       (prov.review_outcome ? ` (${prov.review_outcome.replaceAll("_", " ")})` : "") : (prov.review_status || "unreviewed").replaceAll("_", " ")}` : "";
  $("draft").style.color = reviewed ? "var(--muted)" : "var(--warn)";
  const errs = $("errors"); errs.replaceChildren(...d.errors.map(e => mk("li", {}, e))); errs.hidden = ok;
  $("prompt").textContent = d.prompt;
  renderEssay(d); drawGraph(d); legend(); if (mode === "prop") drawProps(d);
  details('<span class="k">Click a node or an edge.</span>');
}
function drawProps(d) {
  const P = d.props, byId = Object.fromEntries(P.propositions.map(p => [p.id, p]));
  const out = {}; P.edges.forEach(e => (out[e.source] ||= []).push(e));
  $("props").replaceChildren(mk("p", {class: "k"}, `${P.propositions.length} propositions from ${d.units.length} units: each unit joined with its reporting frame, conditions and split-off parts.`),
    ...P.propositions.map(p => {
      const el = mk("div", {class: "prop"});
      el.style.setProperty("--c", `var(--${p.role})`);
      el.append(mk("span", {class: "ptag"}, `${p.id} · ${p.role}${p.stance !== "endorsed" ? " · " + p.stance : ""}${p.polarity === "negative" ? " · negated" : ""}`), p.text);
      (out[p.id] || []).forEach(e => el.append(mk("div", {class: "pout"},
        `${e.tier === "secondary" ? "(secondary) " : ""}${e.label} → ${e.target}: ${byId[e.target].text.slice(0, 70)}${byId[e.target].text.length > 70 ? "…" : ""}`)));
      el.onmouseenter = () => { el.classList.add("hl"); p.units.forEach(u => hl(u, true)); };
      el.onmouseleave = () => { el.classList.remove("hl"); p.units.forEach(u => hl(u, false)); };
      return el;
    }));
}
function setMode(m) { mode = m; ["rel", "arg", "prop"].forEach(k => $("v-" + k).setAttribute("aria-pressed", m === k));
  $("graph").hidden = m === "prop"; $("props").hidden = m !== "prop"; $("fit").hidden = $("all").hidden = m === "prop";
  if (m === "prop") { drawProps(DATA.essays[cur]); return; }
  const v = view; drawGraph(DATA.essays[cur]); if (v) setView(v); legend(); }
$("v-rel").onclick = () => setMode("rel");
$("v-arg").onclick = () => setMode("arg");
$("v-prop").onclick = () => setMode("prop");
$("fit").onclick = fitWidth;
$("all").onclick = fitAll;
DATA.essays.forEach((d, i) => $("pick").append(mk("option", {value: i}, d.id.replace("persuade:", ""))));
$("pick").onchange = e => show(+e.target.value);
$("pick").hidden = DATA.essays.length < 2;
window.addEventListener("resize", () => box && fitWidth());
show(0);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, action="append", required=True, help="argument_graph JSON (repeatable)")
    parser.add_argument("--records", type=Path, required=True, help="records.jsonl or pilot.jsonl holding the essays")
    parser.add_argument("--output", type=Path, required=True, help="Output .html file")
    parser.add_argument("--title", default="Argument graph")
    args = parser.parse_args()
    graphs = [json.loads(p.read_text()) for p in args.graph]
    wanted = {g["example_id"] for g in graphs}
    with args.records.open() as handle:
        records = {r["example_id"]: r for r in map(json.loads, handle) if r["example_id"] in wanted}
    missing = wanted - set(records)
    if missing:
        parser.error(f"Essays not found in records: {sorted(missing)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render([(g, records[g["example_id"]]) for g in graphs], args.title), encoding="utf-8")
    print(json.dumps({"graphs": len(graphs), "output": str(args.output)}))


if __name__ == "__main__":
    main()
