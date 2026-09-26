"""Render source graphs (source_graph/0.1) as a self-contained HTML viewer.

Left: each passage with its paragraph numbers, units tinted by type. Right: the author's
argument as an outline: each thesis or claim with the passages that support it, what the
author concedes, and each opposing view with the author's answer. A fact sheet is shown as
its topic groups. Hovering a unit on either side highlights it on the other. Validation
errors are listed, never hidden.
"""
import argparse
import html
import json
from pathlib import Path

from .source_graph import validate_source_graph


def render(pairs, title="Source graphs"):
    data = [{"id": r["example_id"], "title": r["metadata"].get("title"), "author": r["metadata"].get("author"),
             "text": r["response_text"], "paragraphs": r["metadata"]["paragraphs"], "units": g["units"], "edges": g["edges"],
             "errors": validate_source_graph(g, r["response_text"], r["metadata"]["paragraphs"]),
             "review": (g.get("provenance") or {}).get("review_status")} for g, r in pairs]
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
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
  --thesis: #0072b2; --claim: #3a9ad9; --fact: #009e73; --example: #e69f00; --concession: #cc79a7;
  --opposing_view: #d55e00; --framing: #9a9a9a; --tint: 14%; --tint-hl: 38%; color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #161618; --panel: #1f1f22; --ink: #ececef; --muted: #9a9aa2; --line: #333338; --warn: #ff8a80;
          --tint: 22%; --tint-hl: 48%; color-scheme: dark; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--bg); border-bottom: 1px solid var(--line);
         padding: 10px 20px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
header h1 { font-size: 16px; margin: 0; font-weight: 600; }
select { font: inherit; font-size: 13px; color: inherit; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 4px 9px; }
.meta { color: var(--muted); font-size: 13px; }
.warn { color: var(--warn); font-size: 13px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 12px; font-size: 12px; color: var(--muted); }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; background: var(--c); vertical-align: -1px; }
main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 18px; padding: 18px 20px; }
@media (max-width: 1000px) { main { grid-template-columns: 1fr; } }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; min-width: 0; max-height: calc(100vh - 110px); overflow: auto; }
h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 10px; font-weight: 600; }
.para { display: grid; grid-template-columns: 28px 1fr; gap: 6px; margin: 0 0 12px; line-height: 1.85; }
.pnum { color: var(--muted); font-size: 12px; text-align: right; padding-top: 3px; }
.u { background: color-mix(in srgb, var(--c) var(--tint), transparent); border-bottom: 2px solid var(--c); border-radius: 3px; padding: 1px 0; cursor: default; }
.u.hl { background: color-mix(in srgb, var(--c) var(--tint-hl), transparent); }
.node { border-left: 3px solid var(--c); padding: 4px 0 4px 10px; margin: 6px 0; }
.node.hl { background: color-mix(in srgb, var(--c) var(--tint), transparent); }
.chip { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--c); font-weight: 600; margin-right: 6px; }
.ref { color: var(--muted); font-size: 12px; margin-left: 6px; }
.edge { margin: 4px 0 4px 14px; }
.elabel { font-size: 12px; color: var(--muted); }
.note { font-size: 12px; color: var(--muted); font-style: italic; }
.passage { margin: 2px 0 6px 0; padding: 0; list-style: none; }
.passage > li > .node { margin: 3px 0; }
.empty { color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <select id="pick" aria-label="Source"></select>
  <span class="meta" id="meta"></span>
  <span class="warn" id="status"></span>
  <span class="legend" id="legend"></span>
</header>
<main>
  <section><h2>Passage</h2><div id="text"></div></section>
  <section><h2>Argument</h2><div id="outline"></div></section>
</main>
<script>
const DATA = __DATA__;
const TYPES = ["thesis", "claim", "fact", "example", "concession", "opposing_view", "framing"];
const LABEL = {supports: "supported by", concedes: "despite (conceded)", opposes: "answered by", elaborates: "detail"};
const $ = id => document.getElementById(id);
const mk = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); Object.assign(e, attrs); e.append(...kids); return e; };
const color = t => `var(--${t})`;
$("legend").append(...TYPES.map(t => { const s = mk("span", {}, t.replace("_", " ")); s.style.setProperty("--c", color(t)); return s; }));

function highlight(uid, on) { document.querySelectorAll(`[data-u="${uid}"]`).forEach(e => e.classList.toggle("hl", on)); }
function hoverable(el, uid) { el.dataset.u = uid; el.onmouseenter = () => highlight(uid, true); el.onmouseleave = () => highlight(uid, false); return el; }

function show(i) {
  const d = DATA[i], byId = Object.fromEntries(d.units.map(u => [u.id, u]));
  $("meta").textContent = `${d.title} — ${d.author}`;
  $("status").textContent = (d.errors.length ? `${d.errors.length} contract errors: ${d.errors.slice(0, 3).join("; ")}` : "")
                            + (d.review && d.review !== "human_reviewed" ? `  Draft (${d.review})` : "");
  // Passage, split by paragraph with its number.
  const paras = Object.entries(d.paragraphs).map(([n, [a, b]]) => ({n, a, b}));
  const blocks = []; let cur = null;
  d.units.forEach(u => {
    const p = paras.find(p => p.a <= u.start && u.start < p.b);
    const key = p ? p.n : `h${u.id}`;
    if (!cur || cur.key !== key) { cur = {key, n: p ? p.n : "", units: []}; blocks.push(cur); }
    cur.units.push(u);
  });
  $("text").replaceChildren(...blocks.map(b => mk("div", {className: "para"}, mk("span", {className: "pnum"}, b.n),
    mk("div", {}, ...b.units.flatMap((u, k) => {
      const s = hoverable(mk("span", {className: "u", title: `${u.id} · ${u.type.replace("_", " ")}`}, u.text), u.id);
      s.style.setProperty("--c", color(u.type));
      return k ? [" ", s] : [s];
    })))));
  // Outline: roots are edge targets that are never part of a passage.
  const incoming = {}, inPassage = new Set();
  d.edges.forEach(e => { (incoming[e.to] ||= []).push(e); e.from.forEach(x => inPassage.add(x)); });
  const order = t => ({thesis: 0, claim: 1, opposing_view: 2}[t] ?? 3);
  const roots = Object.keys(incoming).filter(x => !inPassage.has(x)).sort((a, b) => order(byId[a].type) - order(byId[b].type) || byId[a].start - byId[b].start);
  const node = (uid, depth, seen) => {
    const u = byId[uid];
    const el = hoverable(mk("div", {className: "node"}, mk("span", {className: "chip"}, u.type.replace("_", " ")), u.text,
                           mk("span", {className: "ref"}, u.paragraph ? `¶${u.paragraph}` : "")), uid);
    el.style.setProperty("--c", color(u.type));
    if (seen.has(uid) || depth > 12) return el;
    const next = new Set(seen).add(uid);
    (incoming[uid] || []).forEach(e => el.append(mk("div", {className: "edge"},
      mk("div", {className: "elabel"}, LABEL[e.type], e.note ? mk("span", {className: "note"}, ` — ${e.note}`) : ""),
      mk("ul", {className: "passage"}, ...e.from.map(x => mk("li", {}, node(x, depth + 1, next)))))));
    return el;
  };
  $("outline").replaceChildren(...(roots.length ? roots.map(r => node(r, 0, new Set())) : [mk("p", {className: "empty"}, "No edges.")]));
}
DATA.forEach((d, i) => $("pick").append(mk("option", {value: i}, `${d.id.replace("source:", "")} — ${d.title}`)));
$("pick").onchange = e => show(+e.target.value);
show(0);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, action="append", required=True, help="source_graph JSON (repeatable)")
    parser.add_argument("--records", type=Path, required=True, help="source_records.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Source graphs")
    args = parser.parse_args()
    graphs = [json.loads(p.read_text()) for p in args.graph]
    with args.records.open() as handle:
        records = {r["example_id"]: r for r in map(json.loads, handle)}
    missing = {g["example_id"] for g in graphs} - set(records)
    if missing:
        parser.error(f"Sources not found in records: {sorted(missing)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render([(g, records[g["example_id"]]) for g in graphs], args.title), encoding="utf-8")
    print(json.dumps({"graphs": len(graphs), "output": str(args.output)}))


if __name__ == "__main__":
    main()
