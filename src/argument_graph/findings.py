"""Turn a student graph and its source alignment into findings for review (Phase C, first version).

Rules only, no model calls. Inputs are the student graph, its alignment (from `align`), the source
units and the assignment's explicit expectations. Every finding carries the student units and
source units it rests on, a short rationale, what it depends on, and `review_status:
needs_review`: these are candidates for a teacher or researcher to check, not diagnoses.

Finding types (plan section 5, Phase C):
- possible_misconception: a unit the judge aligned as `distorted`. Whether the student asserts it
  or reports it is recorded; a misread source is a candidate either way.
- unsupported_claim: a claim the student offers as a reason (role claim, endorsed, and either the
  root or the satellite of an explanation relation) that receives no derived support in the graph
  (`argument_edges`), directly, through a joint-list or same-unit partner, or through a later unit
  that restates it, and has no basis in the
  sources. Conditions, frames and other parts of a claim are not judged on their own.
- missing_required_content: an explicit requirement of the assignment that the essay does not
  appear to meet (claim, counterclaim, several sources, not over-relying on one, several paragraphs).
The letter form (E1) is not checked and is listed as such.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from .align import load_sources
from .graph_schema import argument_edges

OVER_RELIANCE = 0.75  # provisional: share of source-based units from a single source
MIN_SOURCE_UNITS = 4  # below this, over-reliance is not judged
SOURCE_BASED = {"quote", "paraphrase", "distorted", "related"}


def source_use(alignments, source_units):
    """Count source-based units per source and label."""
    per_source, labels = Counter(), Counter()
    for a in alignments.values():
        labels[a["label"]] += 1
        if a["label"] in SOURCE_BASED:
            for sid in sorted({source_units[s]["source"] for s in a["source_units"] if s in source_units}):
                per_source[sid] += 1
    based = sum(labels[x] for x in SOURCE_BASED)
    return {"labels": dict(labels), "source_based_units": based, "units_per_source": dict(sorted(per_source.items()))}


def build(record, graph, alignments, source_units, expectations):
    units = {u["id"]: u for u in graph["units"]}
    exp = {e["id"]: e for e in expectations["expectations"]}
    findings = []

    def add(kind, rationale, unit_ids=(), src=(), criterion=None, depends_on=(), **extra):
        findings.append(dict({"id": f"F{len(findings) + 1}", "type": kind, "units": list(unit_ids),
                              "student_text": [units[u]["text"] for u in unit_ids], "source_units": list(src),
                              "source_text": [{"id": s, "source": source_units[s]["source"], "paragraph": source_units[s].get("paragraph"),
                                               "text": source_units[s]["text"]} for s in src if s in source_units],
                              "criterion": criterion, "rationale": rationale, "depends_on": list(depends_on),
                              "review_status": "needs_review"}, **extra))

    for uid, a in alignments.items():
        if a["label"] == "distorted" and uid in units:
            add("possible_misconception", a.get("note") or "Changes the meaning of the source.", [uid], a["source_units"],
                depends_on=["alignment"], student_stance=units[uid].get("stance"))

    supported = {e["target"] for e in argument_edges(graph) if e["type"] == "support"}
    head = {r["source"]: r for r in graph["relations"] if r["tier"] == "primary"}
    group = {uid: uid for uid in units}  # members of a joint-list or same-unit share their support
    def find(x):
        while group[x] != x:
            x = group[x]
        return x
    for r in graph["relations"]:
        if r["label"] in ("joint-list", "same-unit") and r["source"] in group and r["target"] in group:
            group[find(r["source"])] = find(r["target"])
    supported |= {uid for uid in units if find(uid) in {find(x) for x in supported if x in units}}
    for r in graph["relations"]:  # a preview counts as supported when a unit restating it is supported
        if r["label"].startswith("restatement") and r["source"] in supported:
            supported.add(r["target"])
    offered = {uid for uid in units if uid == graph.get("root") or
               (uid in head and head[uid]["label"] in ("explanation-justify", "explanation-evidence"))}
    for uid, u in units.items():
        if u.get("role") == "claim" and u.get("stance") == "endorsed" and uid in offered and uid not in supported \
                and alignments.get(uid, {}).get("label", "none") == "none":
            add("unsupported_claim", "A claim with no reason or evidence attached in the essay and no basis in the sources.",
                [uid], depends_on=["extraction", "alignment"])

    use = source_use(alignments, source_units)
    roles = Counter(u.get("role") for u in units.values())
    stances = Counter(u.get("stance") for u in units.values())
    checks = {}
    checks["E3"] = bool(roles["position"] or roles["claim"])
    checks["E4"] = bool(roles["counterclaim"] or stances["conceded"] or stances["rejected"] or stances["reported"])
    checks["E7"] = use["source_based_units"] > 0
    checks["E5"] = len(use["units_per_source"]) >= 2
    top = max(use["units_per_source"].values(), default=0)
    checks["E6"] = None if use["source_based_units"] < MIN_SOURCE_UNITS else top / use["source_based_units"] <= OVER_RELIANCE
    paragraphs = [p for p in record["response_text"].split("\n\n") if p.strip()]
    checks["E8"] = len(paragraphs) >= 3
    reasons = {
        "E3": ("No unit states a position or claim.", ["extraction"]),
        "E4": ("No counterclaim: no unit is marked counterclaim, conceded, rejected or reported.", ["extraction"]),
        "E7": ("No unit draws on the sources.", ["alignment"]),
        "E5": (f"Evidence comes from {len(use['units_per_source'])} source(s): {', '.join(use['units_per_source']) or 'none'}.", ["alignment"]),
        "E6": (f"{top} of {use['source_based_units']} source-based units come from one source (threshold {OVER_RELIANCE:.0%}, provisional).", ["alignment"]),
        "E8": (f"{len(paragraphs)} paragraph(s).", []),
    }
    for eid, ok in checks.items():
        if ok is False:
            add("missing_required_content", reasons[eid][0], criterion={"id": eid, "text": exp[eid]["criterion"]},
                depends_on=reasons[eid][1])
    status = {eid: ("met" if ok else "not met" if ok is False else "not judged") for eid, ok in checks.items()}
    status.update({eid: "not checked" for eid in exp if eid not in status})
    return {"example_id": record["example_id"], "source_use": use,
            "expectations": dict(sorted(status.items())), "findings": findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--align-run", type=Path, required=True, help="Folder of <id>.align.json files from `align run`")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--sources", type=Path, default=Path("data/sources/electoral_college"))
    parser.add_argument("--expectations", type=Path, default=Path("data/annotations/reference/electoral_college_expectations.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/runs/findings"))
    args = parser.parse_args()
    source_units, _ = load_sources(args.sources)
    expectations = json.loads(args.expectations.read_text())
    records = {json.loads(l)["example_id"]: json.loads(l) for l in open(args.records)}
    out_dir = args.output_dir / args.align_run.name
    out_dir.mkdir(parents=True, exist_ok=True)
    totals = Counter()
    for path in sorted(args.align_run.glob("*.align.json")):
        aligned = json.loads(path.read_text())
        graph = json.loads(Path(aligned["student_graph"]).read_text())
        report = build(records[aligned["example_id"]], graph, aligned["alignments"], source_units, expectations)
        report["inputs"] = {"student_graph": aligned["student_graph"], "alignment": str(path)}
        (out_dir / path.name.replace(".align.json", ".findings.json")).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        kinds = Counter(f["type"] for f in report["findings"])
        totals.update(kinds)
        print(f"{aligned['example_id'].split(':')[-1]}: {dict(kinds)}  sources {report['source_use']['units_per_source']}  "
              f"unmet {[e for e, s in report['expectations'].items() if s == 'not met']}")
    print(json.dumps({"output": str(out_dir), "findings": dict(totals)}))


if __name__ == "__main__":
    main()
