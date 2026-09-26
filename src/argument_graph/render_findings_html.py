"""Render findings (from `findings`) as a self-contained review page.

Left: the essay, units tinted by how they use the sources (quote, paraphrase, distorted,
related, none). Right: the requirement checklist, source use per source, and each finding with
the student's words beside the source passage it concerns. Hovering a finding highlights its
units. The page quotes the source passages, so write it under a gitignored folder.
"""
import argparse
import html
import json
from pathlib import Path


def render(reports, title="Findings for review"):
    payload = json.dumps(reports, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root { --bg: #fafaf8; --panel: #ffffff; --ink: #1d1d1f; --muted: #6b6b70; --line: #e3e3e0; --warn: #b3261e;
        --quote: #0072b2; --paraphrase: #009e73; --distorted: #d55e00; --related: #e69f00; --none: transparent;
        --ok: #009e73; --tint: 16%; --tint-hl: 42%; color-scheme: light; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161618; --panel: #1f1f22; --ink: #ececef; --muted: #9a9aa2; --line: #333338; --warn: #ff8a80;
          --tint: 24%; --tint-hl: 50%; color-scheme: dark; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--bg); border-bottom: 1px solid var(--line); padding: 10px 20px;
         display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
header h1 { font-size: 16px; margin: 0; font-weight: 600; }
select { font: inherit; font-size: 13px; color: inherit; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 4px 9px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 12px; font-size: 12px; color: var(--muted); }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px;
                       background: var(--c); border: 1px solid var(--line); vertical-align: -1px; }
main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; padding: 18px 20px; }
@media (max-width: 1000px) { main { grid-template-columns: 1fr; } }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; min-width: 0;
          max-height: calc(100vh - 110px); overflow: auto; }
h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 14px 0 8px; font-weight: 600; }
h2:first-child { margin-top: 0; }
#essay { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.9; }
.u { background: color-mix(in srgb, var(--c) var(--tint), transparent); border-bottom: 2px solid var(--c); border-radius: 3px; padding: 1px 0; }
.u.hl { background: color-mix(in srgb, var(--c) var(--tint-hl), transparent); outline: 2px solid var(--warn); }
.checks { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; font-size: 13px; }
.st-met { color: var(--ok); } .st-not { color: var(--warn); font-weight: 600; } .st-other { color: var(--muted); }
.bars { font-size: 13px; }
.bar { display: grid; grid-template-columns: 30px 1fr 30px; gap: 8px; align-items: center; margin: 3px 0; }
.bar i { display: block; height: 10px; border-radius: 3px; background: var(--quote); }
.finding { border: 1px solid var(--line); border-left: 4px solid var(--c); border-radius: 6px; padding: 8px 10px; margin: 8px 0; }
.finding .kind { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; font-weight: 600; color: var(--c); }
.finding .why { margin: 4px 0; }
.q { font-size: 13px; margin: 4px 0; padding-left: 8px; border-left: 2px solid var(--line); }
.q b { color: var(--muted); font-weight: 600; margin-right: 4px; }
.meta { color: var(--muted); font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <select id="pick" aria-label="Essay"></select>
  <span class="legend" id="legend"></span>
</header>
<main>
  <section><h2>Essay</h2><div id="essay"></div></section>
  <section id="side"></section>
</main>
<script>
const DATA = __DATA__;
const LABELS = ["quote", "paraphrase", "distorted", "related", "none"];
const KIND = {possible_misconception: ["Possible misconception", "var(--distorted)"],
              unsupported_claim: ["Unsupported claim", "var(--related)"],
              missing_required_content: ["Missing required content", "var(--quote)"]};
const $ = id => document.getElementById(id);
const mk = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); Object.assign(e, attrs); e.append(...kids); return e; };
$("legend").append(...LABELS.map(l => { const s = mk("span", {}, l); s.style.setProperty("--c", `var(--${l})`); return s; }));
function show(i) {
  const d = DATA[i];
  const text = d.text, parts = []; let pos = 0;
  [...d.units].sort((a, b) => a.start - b.start).forEach(u => {
    if (u.start > pos) parts.push(text.slice(pos, u.start));
    const s = mk("span", {className: "u", title: `${u.id} · ${u.label}${u.sources.length ? " · " + u.sources.join(", ") : ""}`}, text.slice(u.start, u.end));
    s.dataset.u = u.id; s.style.setProperty("--c", `var(--${u.label})`); parts.push(s); pos = u.end;
  });
  parts.push(text.slice(pos));
  $("essay").replaceChildren(...parts);
  const side = [mk("h2", {}, "Assignment requirements")];
  side.push(mk("div", {className: "checks"}, ...Object.entries(d.expectations).flatMap(([k, v]) => [
    mk("span", {className: v === "met" ? "st-met" : v === "not met" ? "st-not" : "st-other"}, v),
    mk("span", {}, `${k}: ${d.criteria[k] || ""}`)])));
  side.push(mk("h2", {}, "Source use"));
  const counts = d.source_use.units_per_source, most = Math.max(1, ...Object.values(counts));
  side.push(mk("div", {className: "bars"}, ...["S1", "S2", "S3"].map(s => {
    const n = counts[s] || 0, bar = mk("i"); bar.style.width = `${100 * n / most}%`;
    return mk("div", {className: "bar"}, mk("span", {}, s), mk("span", {}, bar), mk("span", {}, String(n)));
  }), mk("div", {className: "meta"}, `${d.source_use.source_based_units} of ${d.units.length} units draw on the sources (a unit can draw on several). S1 Federal Register, S2 Plumer, S3 Posner.`)));
  side.push(mk("h2", {}, `Findings (${d.findings.length}) — all need review`));
  d.findings.forEach(f => {
    const [name, c] = KIND[f.type] || [f.type, "var(--muted)"];
    const card = mk("div", {className: "finding"}, mk("div", {className: "kind"}, name + (f.student_stance && f.student_stance !== "endorsed" ? ` (student ${f.student_stance} it)` : "")),
      mk("div", {className: "why"}, f.criterion ? `${f.criterion.id}: ${f.criterion.text} — ${f.rationale}` : f.rationale),
      ...f.student_text.map(t => mk("div", {className: "q"}, mk("b", {}, "Student"), t)),
      ...f.source_text.map(s => mk("div", {className: "q"}, mk("b", {}, `${s.source} ¶${s.paragraph ?? "-"}`), s.text)),
      mk("div", {className: "meta"}, `Depends on: ${f.depends_on.join(", ") || "text"}`));
    card.style.setProperty("--c", c);
    card.onmouseenter = () => f.units.forEach(u => document.querySelectorAll(`[data-u="${u}"]`).forEach(e => e.classList.add("hl")));
    card.onmouseleave = () => document.querySelectorAll(".u.hl").forEach(e => e.classList.remove("hl"));
    side.push(card);
  });
  $("side").replaceChildren(...side);
}
DATA.forEach((d, i) => $("pick").append(mk("option", {value: i}, `${d.id.replace("persuade:", "")} — ${d.findings.length} findings`)));
$("pick").onchange = e => show(+e.target.value);
show(0);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings-dir", type=Path, required=True, help="Folder of <id>.findings.json")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, default=Path("data/annotations/reference/electoral_college_expectations.json"))
    parser.add_argument("--output", type=Path, help="Default: <findings-dir>/findings.html")
    args = parser.parse_args()
    records = {json.loads(l)["example_id"]: json.loads(l) for l in open(args.records)}
    criteria = {e["id"]: e["criterion"] for e in json.loads(args.expectations.read_text())["expectations"]}
    reports = []
    for path in sorted(args.findings_dir.glob("*.findings.json")):
        r = json.loads(path.read_text())
        graph = json.loads(Path(r["inputs"]["student_graph"]).read_text())
        aligned = json.loads(Path(r["inputs"]["alignment"]).read_text())["alignments"]
        units = [{"id": u["id"], "start": u["start"], "end": u["end"], "label": aligned.get(u["id"], {}).get("label", "none"),
                  "sources": aligned.get(u["id"], {}).get("source_units", [])} for u in graph["units"]]
        reports.append({"id": r["example_id"], "text": records[r["example_id"]]["response_text"], "units": units,
                        "expectations": r["expectations"], "criteria": criteria, "source_use": r["source_use"], "findings": r["findings"]})
    out = args.output or args.findings_dir / "findings.html"
    out.write_text(render(reports), encoding="utf-8")
    print(json.dumps({"essays": len(reports), "output": str(out)}))


if __name__ == "__main__":
    main()
