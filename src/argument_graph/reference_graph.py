"""Convert the self-annotated sheets into argument_graph/0.1 reference graphs.

The sheets carry the author's labels (role, stance, parent, how it relates). This module maps
them onto the system's inventory so `evaluate.py` can score extracted graphs against them. The
mapping is a modelling choice and is documented in docs/SELF_ANNOTATION.md.

Not annotated by the author, so filled with fixed values: polarity (always "positive") and
signals (every relation is implicit). Neither is scored.
"""
import argparse
import csv
import json
import re
from pathlib import Path

from .graph_schema import SCHEMA_VERSION, validate_graph

ROLE = {"Lead": "lead", "Position": "position", "Claim": "claim", "Evidence": "evidence",
        "Counterclaim": "counterclaim", "Rebuttal": "rebuttal", "Conclusion": "concluding_summary",
        "Other": "unannotated"}
STANCE = {"Endorsed": "endorsed", "Conceded": "conceded", "Rejected": "rejected",
          "Reported": "reported", "Unclear": "unclear"}
HOW = {"gives an example": "explanation-evidence", "adds detail": "elaboration-additional",
       "restates it": "restatement-partial", "sets the scene": "context-background",
       "other: sets a condition": "contingency-condition"}
# Free-text "other: ..." relations with no direct counterpart fall back to the default label.
DEFAULT_LABEL = "elaboration-additional"
COLUMNS = {"role": "What is the segment doing?", "stance": "Is this the writer's stance?",
           "parent": "Segment it relates to", "how": "How it relates"}


def read_sheet(path):
    """Segment rows of one sheet (the overall-comment rows have no segment text)."""
    with Path(path).open(newline="") as handle:
        return [r for r in csv.DictReader(handle) if r["segment_text"]]


def locate(text, rows):
    """Offsets of each row's segment as an in-order exact slice of the essay."""
    spans, pos = [], 0
    for r in rows:
        start = text.find(r["segment_text"], pos)
        if start < 0:
            raise ValueError(f"essay {r['essay_no']} segment {r['segment_no']}: text not found after offset {pos}")
        spans.append((start, start + len(r["segment_text"])))
        pos = spans[-1][1]
    return spans


def relation_label(child, parent, how):
    """System relation for one sheet edge, from the child's side (child = satellite)."""
    stance, p_stance = child["stance"], parent["stance"]
    if how in ("argues against it", "contrasts with it"):
        if stance == "conceded":
            return "adversative-concession"
        if stance == "rejected":
            return "adversative-antithesis"
        return "adversative-contrast"
    if how == "backs it up":
        return "explanation-justify" if parent["role"] in ("position", "claim") else "explanation-evidence"
    return HOW.get(how, DEFAULT_LABEL)


def to_graph(example_id, text, rows):
    """Build the graph; a counterclaim's reply becomes its head (see `flip_replies`)."""
    spans = locate(text, rows)
    by_no = {r["segment_no"]: i for i, r in enumerate(rows)}
    units = [{"id": r["unit_id"], "start": s, "end": e, "text": text[s:e], "role": ROLE[r[COLUMNS["role"]]],
              "stance": STANCE[r[COLUMNS["stance"]]], "polarity": "positive"}
             for r, (s, e) in zip(rows, spans)]
    heads = {}
    root = None
    for i, r in enumerate(rows):
        parent = r[COLUMNS["parent"]]
        if parent == "TOP":
            root = units[i]["id"]
        else:
            j = by_no[parent[1:]]
            heads[units[i]["id"]] = (units[j]["id"], r[COLUMNS["how"]])
    unit = {u["id"]: u for u in units}
    labels = {c: relation_label(unit[c], unit[p], how) for c, (p, how) in heads.items()}
    flip_replies(unit, heads, labels, rows)
    reorder_contrasts(unit, heads, labels, root)
    relations = [{"id": f"r{n}", "source": c, "target": p, "label": labels[c], "tier": "primary", "signals": [],
                  "implicit": True} for n, (c, (p, _)) in enumerate(heads.items(), 1)]
    return {"schema_version": SCHEMA_VERSION, "example_id": example_id, "root": root,
            "units": units, "relations": relations}


def flip_replies(unit, heads, labels, rows):
    """The author hangs a counterclaim off the position and the reply off the counterclaim. The
    system's adversative relations run the other way (the conceded or rejected unit is the
    satellite of the endorsed one), so the counterclaim becomes the satellite of its first reply,
    and the reply takes over the counterclaim's old head as the writer's reason. Further replies
    to the same counterclaim stay attached to the counterclaim."""
    order = {u: i for i, u in enumerate(unit)}
    for cid in [u for u in unit if unit[u]["role"] == "counterclaim"]:
        replies = sorted((c for c, (p, how) in heads.items()
                          if p == cid and how == "argues against it" and unit[c]["stance"] == "endorsed"),
                         key=order.get)
        if not replies or cid not in heads:
            continue
        reply = replies[0]
        old_head, _ = heads[cid]
        heads[reply] = (old_head, "backs it up")
        labels[reply] = "explanation-justify" if unit[old_head]["role"] in ("position", "claim") else "explanation-evidence"
        heads[cid] = (reply, "argues against it")
        labels[cid] = relation_label(unit[cid], unit[reply], "argues against it")


def reorder_contrasts(unit, heads, labels, root):
    """A contrast is multinuclear and chains the later member to the earlier one, but the author
    hangs a fronted contrast ("Although X, Y") off the later segment. The earlier member takes
    the later member's place in the tree (and its relation to the later member's head), and the
    later member is chained to it. If the later member is the position (the root) it cannot move
    down, so the earlier one stays its satellite as `context-background`."""
    for c in [c for c in heads if labels[c] == "adversative-contrast"]:
        p, _ = heads[c]
        if unit[c]["start"] > unit[p]["start"]:
            continue
        if p == root:
            labels[c] = "context-background"
            continue
        heads[c], labels[c] = heads[p], labels[p]
        heads[p], labels[p] = (c, "contrasts with it"), "adversative-contrast"


def convert(sheets_dir, records_path, out_dir):
    with Path(records_path).open() as handle:
        records = {r["example_id"]: r for r in map(json.loads, handle)}
    out_dir.mkdir(parents=True, exist_ok=True)
    problems = {}
    for sheet in sorted(Path(sheets_dir).glob("Essay *.csv"), key=lambda p: int(re.findall(r"\d+", p.stem)[0])):
        rows = read_sheet(sheet)
        example_id = f"persuade:{rows[0]['example_id']}"
        text = records[example_id]["response_text"]
        try:
            graph = to_graph(example_id, text, rows)
        except ValueError as err:
            problems[sheet.stem] = [str(err)]
            continue
        errors = validate_graph(graph, text)
        if errors:
            problems[sheet.stem] = errors
        (out_dir / f"{rows[0]['example_id']}.json").write_text(json.dumps(graph, indent=2))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheets-dir", type=Path, default=Path("data/annotations/self_annotation_online_learning_30"))
    parser.add_argument("--records", type=Path, default=Path("data/processed/distance_learning_v3/records.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/annotations/self_annotation_online_learning_30/reference_graphs"))
    args = parser.parse_args()
    problems = convert(args.sheets_dir, args.records, args.out_dir)
    for essay, errors in problems.items():
        print(essay)
        for e in errors:
            print("  ", e)
    print(f"{len(list(args.out_dir.glob('*.json')))} graphs written, {len(problems)} essays with problems")


if __name__ == "__main__":
    main()
