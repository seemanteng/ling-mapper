"""Render records as a self-contained HTML viewer: essay text beside its argument tree.

Spans are highlighted in the essay by role; the tree nests each span under its
candidate parent (hierarchy links are unverified). Hover or click either side
to find the matching element on the other.
"""
import argparse
import html
import json
from pathlib import Path

ROLE_ORDER = ["lead", "position", "claim", "counterclaim", "rebuttal", "evidence",
              "concluding_summary", "unannotated"]


def essay_data(rec, include_unannotated=False):
    spans = [g for g in rec["gold_spans"] or [] if include_unannotated or g["role"] != "unannotated"]
    ids = {g["annotation_id"] for g in spans}
    parent_of = {}
    for link in rec["metadata"].get("hierarchy_candidates", []):
        child, parents = link["annotation_id"], link["candidate_parent_ids"]
        if link["status"] == "unique_candidate" and child in ids and parents[0] in ids:
            parent_of[child] = parents[0]
    return {
        "id": rec["example_id"], "score": rec["metadata"].get("holistic_score"),
        "prompt": rec["prompt"], "text": rec["response_text"],
        "spans": [{"id": g["annotation_id"], "role": g["role"], "start": g["start"], "end": g["end"],
                   "parent": parent_of.get(g["annotation_id"])}
                  for g in sorted(spans, key=lambda g: g["start"])],
    }


def render(records, include_unannotated=False, title="Argument viewer"):
    data = [essay_data(r, include_unannotated) for r in records]
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload).replace(
        "__ROLES__", json.dumps(ROLE_ORDER))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #fafaf8; --panel: #ffffff; --ink: #1d1d1f; --muted: #6b6b70; --line: #e3e3e0;
  --lead: #8a8a8a; --position: #0072b2; --claim: #3a9ad9; --counterclaim: #d55e00;
  --rebuttal: #cc79a7; --evidence: #009e73; --concluding_summary: #e69f00; --unannotated: #b8b8b8;
  --tint: 16%; --tint-hl: 38%;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #161618; --panel: #1f1f22; --ink: #ececef; --muted: #9a9aa2; --line: #333338;
          --tint: 24%; --tint-hl: 50%; color-scheme: dark; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--bg); border-bottom: 1px solid var(--line);
         padding: 12px 20px; display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; }
header h1 { font-size: 16px; margin: 0; font-weight: 600; }
select, button { font: inherit; color: inherit; background: var(--panel); border: 1px solid var(--line);
                 border-radius: 6px; padding: 4px 8px; cursor: pointer; }
.meta { color: var(--muted); font-size: 13px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 12px; font-size: 12px; color: var(--muted); }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px;
                       margin-right: 5px; vertical-align: -1px; background: var(--c); }
main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; padding: 20px; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; } }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px;
          min-width: 0; }
section h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
             margin: 0 0 12px; font-weight: 600; }
.pane { max-height: calc(100vh - 150px); overflow: auto; }
#essay { white-space: pre-wrap; overflow-wrap: anywhere; }
mark { color: inherit; background: color-mix(in srgb, var(--c) var(--tint), transparent);
       border-bottom: 2px solid var(--c); border-radius: 2px; cursor: pointer; padding: 1px 0; }
mark.hl { background: color-mix(in srgb, var(--c) var(--tint-hl), transparent); }
.prompt { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
ul.tree, ul.tree ul { list-style: none; margin: 0; padding: 0; }
ul.tree ul { margin-left: 14px; padding-left: 14px; border-left: 2px solid var(--line); }
ul.tree li { margin: 8px 0; }
.card { border: 1px solid var(--line); border-left: 4px solid var(--c); border-radius: 6px;
        padding: 6px 10px; cursor: pointer; background: var(--panel); }
.card.hl { background: color-mix(in srgb, var(--c) var(--tint), var(--panel)); }
.tag { font-size: 11px; font-weight: 700; letter-spacing: .05em; color: var(--c); margin-right: 6px; }
.txt { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card.hl .txt, .card.open .txt { -webkit-line-clamp: unset; }
.kids { font-size: 12px; color: var(--muted); margin-left: 6px; }
.note { font-size: 12px; color: var(--muted); margin-top: 14px; }
main.graph-mode { grid-template-columns: minmax(0, 1fr) minmax(0, 1.7fr); }
.tabs { display: flex; gap: 4px; margin: -4px 0 12px; align-items: center; }
.tabs button { font-size: 13px; }
.tabs button[aria-pressed="true"] { background: var(--ink); color: var(--panel); border-color: var(--ink); }
.tabs .hint { margin-left: auto; font-size: 12px; color: var(--muted); }
#graph { height: calc(100vh - 190px); min-height: 360px; border: 1px solid var(--line); border-radius: 8px;
         cursor: grab; touch-action: none; }
#graph.dragging { cursor: grabbing; }
#graph svg { width: 100%; height: 100%; display: block; }
g.node { cursor: pointer; }
g.node rect { fill: color-mix(in srgb, var(--c) var(--tint), var(--panel)); stroke: var(--c); stroke-width: 1.5; }
g.node.hl rect, g.node.pinned rect { fill: color-mix(in srgb, var(--c) var(--tint-hl), var(--panel)); stroke-width: 3; }
g.node .role { font: 700 11px sans-serif; letter-spacing: .05em; fill: var(--c); }
g.node .body { font: 13px sans-serif; fill: var(--ink); }
path.edge { fill: none; stroke: var(--c); stroke-width: 1.6; opacity: .7; }
path.edge.hl { stroke-width: 3.2; opacity: 1; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <button id="prev" aria-label="Previous essay">←</button>
  <select id="pick" aria-label="Essay"></select>
  <button id="next" aria-label="Next essay">→</button>
  <span class="meta" id="meta"></span>
  <div class="legend" id="legend"></div>
</header>
<main class="graph-mode">
  <section><h2>Essay</h2><div class="pane"><p class="prompt" id="prompt"></p><div id="essay"></div></div></section>
  <section><h2>Argument tree</h2>
    <div class="tabs"><button id="tab-graph" aria-pressed="true">Graph</button><button id="tab-outline" aria-pressed="false">Outline</button>
      <button id="fit" title="Fit graph to view">Fit</button><button id="orient" title="Switch layout direction">↕ Top-down</button><span class="hint">Scroll to zoom · drag to pan · click a node to find it in the essay</span></div>
    <div id="graph"></div>
    <div class="pane" id="outline" hidden><ul class="tree" id="tree"></ul></div>
    <p class="note">Arrows point child → parent, coloured by the child's role. Links are PERSUADE hierarchy candidates (unverified).</p></section>
</main>
<script>
const DATA = __DATA__;
const ROLES = __ROLES__;
const label = r => r.replace("_", " ").toUpperCase();
const colour = r => `var(--${r})`;
const $ = id => document.getElementById(id);
let current = 0;

function el(tag, attrs, text) {
  const e = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => k === "style" ? e.style.setProperty("--c", v) : e.setAttribute(k, v));
  if (text !== undefined) e.textContent = text;
  return e;
}

function show(i) {
  current = (i + DATA.length) % DATA.length;
  const d = DATA[current];
  $("pick").value = current;
  const links = d.spans.filter(s => s.parent).length;
  $("meta").textContent = `score ${d.score ?? "–"} · ${d.spans.length} spans · ${links} links`;
  $("prompt").textContent = d.prompt;
  const essay = $("essay"); essay.replaceChildren();
  let pos = 0;
  for (const s of d.spans) {
    if (s.start > pos) essay.append(d.text.slice(pos, s.start));
    const m = el("mark", {"data-id": s.id, style: colour(s.role), title: label(s.role)}, d.text.slice(s.start, s.end));
    essay.append(m); pos = s.end;
  }
  essay.append(d.text.slice(pos));

  const kids = {}; d.spans.forEach(s => { if (s.parent) (kids[s.parent] ||= []).push(s); });
  const build = (s, seen) => {
    const li = el("li");
    const card = el("div", {class: "card", "data-id": s.id, style: colour(s.role)});
    card.append(el("span", {class: "tag"}, label(s.role)));
    const n = (kids[s.id] || []).length;
    if (n) card.append(el("span", {class: "kids"}, `${n} child${n > 1 ? "ren" : ""}`));
    card.append(el("div", {class: "txt"}, d.text.slice(s.start, s.end).trim()));
    li.append(card);
    const children = (kids[s.id] || []).filter(k => !seen.has(k.id));
    if (children.length) {
      const ul = el("ul"); children.forEach(k => ul.append(build(k, new Set([...seen, k.id])))); li.append(ul);
    }
    return li;
  };
  const tree = $("tree"); tree.replaceChildren();
  d.spans.filter(s => !s.parent).forEach(s => tree.append(build(s, new Set([s.id]))));

  drawGraph(d, kids);

  const counts = {}; d.spans.forEach(s => counts[s.role] = (counts[s.role] || 0) + 1);
  const legend = $("legend"); legend.replaceChildren();
  ROLES.filter(r => counts[r]).forEach(r => legend.append(el("span", {style: colour(r)}, `${label(r)} ${counts[r]}`)));
  try { localStorage.setItem("argviewer-essay", current); } catch (e) {}
}

function highlight(id, on) {
  document.querySelectorAll(`[data-id="${id}"], path.edge[data-from="${id}"], path.edge[data-to="${id}"]`)
    .forEach(e => e.classList.toggle("hl", on));
}

// ---- Graph view: tidy tree, roots on top, children below in essay order ----
const NS = "http://www.w3.org/2000/svg";
const W = 240, H = 78;
const GEOM = {lr: {slot: H + 16, level: W + 70}, tb: {slot: W + 20, level: H + 70}};
let orient = "lr", view = null, fitBox = null, lastDraw = null;
function svg(tag, attrs, text) {
  const e = document.createElementNS(NS, tag);
  Object.entries(attrs || {}).forEach(([k, v]) => k === "style" ? e.style.setProperty("--c", v) : e.setAttribute(k, v));
  if (text !== undefined) e.textContent = text;
  return e;
}
function wrap(text, width = Math.floor((W - 20) / 6.6), lines = 3) {
  const words = text.split(/\s+/).filter(Boolean), out = [];
  let line = "";
  for (const w of words) {
    if ((line + " " + w).trim().length > width) { out.push(line); line = w; if (out.length === lines) break; }
    else line = (line + " " + w).trim();
  }
  if (out.length < lines && line) out.push(line);
  const used = out.join(" ").split(/\s+/).length;
  if (used < words.length) out[out.length - 1] = out[out.length - 1].replace(/.{0,2}$/, "") + "…";
  return out;
}
function layout(d, kids) {
  const pos = {}; let slot = 0;
  const place = (s, depth, seen) => {
    const children = (kids[s.id] || []).filter(k => !seen.has(k.id) && !pos[k.id]);
    children.forEach(k => place(k, depth + 1, new Set([...seen, k.id])));
    const xs = children.map(k => pos[k.id] && pos[k.id].x).filter(x => x !== undefined);
    pos[s.id] = {x: xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : slot++, y: depth};
  };
  d.spans.filter(s => !s.parent).forEach(s => place(s, 0, new Set([s.id])));
  d.spans.forEach(s => { if (!pos[s.id]) place(s, 0, new Set([s.id])); });  // cycles without a root
  const g = GEOM[orient];  // x = sibling slot, y = depth; map to screen for the chosen direction
  Object.values(pos).forEach(p => { const slot = p.x * g.slot, depth = p.y * g.level;
    [p.x, p.y] = orient === "lr" ? [depth, slot] : [slot, depth]; });
  return pos;
}
function setView(v) { view = v; $("graph").firstChild.setAttribute("viewBox", `${v.x} ${v.y} ${v.w} ${v.h}`); }
function fit() { if (fitBox) setView({...fitBox}); }
function drawGraph(d, kids) {
  lastDraw = [d, kids];
  const pos = layout(d, kids), byId = Object.fromEntries(d.spans.map(s => [s.id, s]));
  const root = svg("svg", {preserveAspectRatio: "xMidYMid meet", role: "img", "aria-label": "Argument graph"});
  const defs = svg("defs");
  ROLES.forEach(r => {
    const m = svg("marker", {id: `arrow-${r}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse"});
    m.append(svg("path", {d: "M0,0 L10,5 L0,10 z", fill: colour(r)}));
    defs.append(m);
  });
  root.append(defs);
  const edges = svg("g"), nodes = svg("g");
  for (const s of d.spans) {
    if (!s.parent || !pos[s.parent]) continue;
    const a = pos[s.id], b = pos[s.parent];
    const path = orient === "lr"
      ? (() => { const x1 = a.x, y1 = a.y + H / 2, x2 = b.x + W, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
                 return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`; })()
      : (() => { const x1 = a.x + W / 2, y1 = a.y, x2 = b.x + W / 2, y2 = b.y + H, my = (y1 + y2) / 2;
                 return `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`; })();
    edges.append(svg("path", {class: "edge", "data-from": s.id, "data-to": s.parent, style: colour(s.role),
      d: path, "marker-end": `url(#arrow-${s.role})`}));
  }
  for (const s of d.spans) {
    const p = pos[s.id], text = d.text.slice(s.start, s.end).trim();
    const g = svg("g", {class: "node", "data-id": s.id, style: colour(s.role), transform: `translate(${p.x},${p.y})`});
    g.append(svg("title", {}, `${label(s.role)}: ${text}`));
    g.append(svg("rect", {width: W, height: H, rx: 8}));
    const n = (kids[s.id] || []).length;
    g.append(svg("text", {class: "role", x: 10, y: 18}, label(s.role) + (n ? `  ·  ${n}` : "")));
    wrap(text).forEach((line, i) => g.append(svg("text", {class: "body", x: 10, y: 36 + i * 15}, line)));
    nodes.append(g);
  }
  root.append(edges, nodes);
  $("graph").replaceChildren(root);
  const xs = Object.values(pos).map(p => p.x), ys = Object.values(pos).map(p => p.y), pad = 30;
  fitBox = {x: Math.min(...xs) - pad, y: Math.min(...ys) - pad,
            w: Math.max(...xs) - Math.min(...xs) + W + 2 * pad, h: Math.max(...ys) - Math.min(...ys) + H + 2 * pad};
  fit();
}
(function panZoom() {
  const box = $("graph"); let drag = null;
  const toSvg = e => { const r = box.getBoundingClientRect(), s = Math.max(view.w / r.width, view.h / r.height);
    return {x: view.x + (e.clientX - r.left - (r.width - view.w / s) / 2) * s, y: view.y + (e.clientY - r.top - (r.height - view.h / s) / 2) * s, s}; };
  box.addEventListener("wheel", e => {
    if (!view) return; e.preventDefault();
    const k = Math.exp(e.deltaY * 0.0015), p = toSvg(e);
    setView({x: p.x - (p.x - view.x) * k, y: p.y - (p.y - view.y) * k, w: view.w * k, h: view.h * k});
  }, {passive: false});
  box.addEventListener("pointerdown", e => { if (view) drag = {cx: e.clientX, cy: e.clientY, v: {...view}, s: toSvg(e).s, moved: false}; });
  window.addEventListener("pointermove", e => {
    if (!drag) return;
    const dx = e.clientX - drag.cx, dy = e.clientY - drag.cy;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; box.classList.add("dragging"); }
    if (drag.moved) setView({...drag.v, x: drag.v.x - dx * drag.s, y: drag.v.y - dy * drag.s});
  });
  window.addEventListener("pointerup", () => { if (drag && drag.moved) box.dataset.justDragged = "1"; drag = null; box.classList.remove("dragging"); });
})();
function setTab(graph) {
  $("tab-graph").setAttribute("aria-pressed", graph); $("tab-outline").setAttribute("aria-pressed", !graph);
  $("graph").hidden = !graph; $("outline").hidden = graph; $("fit").hidden = $("orient").hidden = !graph;
  document.querySelector("main").classList.toggle("graph-mode", graph);
  try { localStorage.setItem("argviewer-tab", graph ? "graph" : "outline"); } catch (e) {}
}
$("tab-graph").onclick = () => setTab(true);
$("tab-outline").onclick = () => setTab(false);
$("fit").onclick = fit;
function setOrient(o) {
  orient = o;
  $("orient").textContent = o === "lr" ? "↕ Top-down" : "↔ Left-to-right";
  if (lastDraw) drawGraph(...lastDraw);
  try { localStorage.setItem("argviewer-orient", o); } catch (e) {}
}
$("orient").onclick = () => setOrient(orient === "lr" ? "tb" : "lr");
document.addEventListener("mouseover", e => { const t = e.target.closest("[data-id]"); if (t) highlight(t.dataset.id, true); });
document.addEventListener("mouseout", e => { const t = e.target.closest("[data-id]"); if (t) highlight(t.dataset.id, false); });
document.addEventListener("click", e => {
  if ($("graph").dataset.justDragged) { delete $("graph").dataset.justDragged; return; }
  const t = e.target.closest("[data-id]"); if (!t) return;
  if (t.tagName === "MARK" && !$("graph").hidden) {
    document.querySelectorAll("g.node.pinned").forEach(n => n.classList.remove("pinned", "hl"));
    const node = document.querySelector(`g.node[data-id="${t.dataset.id}"]`);
    if (node) node.classList.add("pinned", "hl");
    return;
  }
  const other = t.tagName === "MARK" ? document.querySelector(`.card[data-id="${t.dataset.id}"]`)
                                     : document.querySelector(`mark[data-id="${t.dataset.id}"]`);
  if (t.classList.contains("card")) t.classList.toggle("open");
  if (other) { other.scrollIntoView({behavior: "smooth", block: "center"}); other.classList.add("open"); }
});

DATA.forEach((d, i) => $("pick").append(el("option", {value: i}, `${i + 1}. ${d.id.replace("persuade:", "")} (score ${d.score ?? "–"})`)));
$("pick").onchange = e => show(+e.target.value);
$("prev").onclick = () => show(current - 1);
$("next").onclick = () => show(current + 1);
document.addEventListener("keydown", e => {
  if (e.target.tagName === "SELECT") return;
  if (e.key === "ArrowLeft") show(current - 1);
  if (e.key === "ArrowRight") show(current + 1);
});
let start = 0, tab = "graph";
try { start = +localStorage.getItem("argviewer-essay") || 0; tab = localStorage.getItem("argviewer-tab") || "graph";
      orient = localStorage.getItem("argviewer-orient") === "tb" ? "tb" : "lr"; } catch (e) {}
$("orient").textContent = orient === "lr" ? "↕ Top-down" : "↔ Left-to-right";
show(start);
setTab(tab !== "outline");
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="records.jsonl or pilot.jsonl")
    parser.add_argument("--output", type=Path, required=True, help="Output .html file")
    parser.add_argument("--essay", action="append", help="Example ID to include (repeatable); default all")
    parser.add_argument("--include-unannotated", action="store_true")
    parser.add_argument("--title", default="Argument viewer")
    args = parser.parse_args()
    with args.records.open() as handle:
        records = [json.loads(line) for line in handle]
    if args.essay:
        records = [r for r in records if r["example_id"] in set(args.essay)]
        if not records:
            parser.error("No matching essays")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(records, args.include_unannotated, args.title), encoding="utf-8")
    print(json.dumps({"essays": len(records), "output": str(args.output)}))


if __name__ == "__main__":
    main()
