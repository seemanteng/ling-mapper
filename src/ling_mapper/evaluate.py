"""Score extracted argument graphs against development gold graphs and PERSUADE.

All overlaps count non-whitespace characters, so unit boundaries inside a token
(e.g. "possible-it") are handled. Two references, as in plan section 7:

Against gold argument graphs (same essay, possibly different segmentation):
  - segmentation: exact unit-span P/R/F1 and unit-boundary P/R/F1;
  - role and stance agreement per character;
  - tree: root match (predicted root covers at least half of the gold root), and for every non-root gold unit whether the predicted
    structure attaches it to the same gold head (attachment), with the same label
    (labelled) or the same coarse class (class). Predicted units are mapped to the
    gold unit they overlap most; a gold unit's predicted attachment is the edge that
    leaves the group of predicted units mapped to it (the shallowest one if several),
    so a finer or coarser segmentation is not by itself counted as an attachment error;
  - derived support/attack edges: P/R/F1 after the same mapping.

Against PERSUADE (every essay):
  - role agreement per character with the gold elements (unannotated elsewhere);
  - element F1 in the Feedback Prize style: predicted elements are maximal runs of
    consecutive units with the same role, matched one-to-one to gold elements of that
    role when overlap is at least half of both; per-role and macro F1. Adjacent
    elements of the same role merge in this projection;
  - attachment of gold elements that have a unique hierarchy parent, using the same
    exit-edge projection onto elements.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .graph_schema import argument_edges

CLASSES = ("explanation", "adversative", "causal", "contingency", "elaboration", "restatement", "attribution",
           "evaluation", "context", "organization", "joint", "mode", "topic", "same")


def coarse(label):
    return next(c for c in CLASSES if label.startswith(c))


class Text:
    def __init__(self, text):
        self.prefix = [0]
        for ch in text:
            self.prefix.append(self.prefix[-1] + (not ch.isspace()))
        self.text = text

    def size(self, a, b):
        return self.prefix[b] - self.prefix[a]

    def overlap(self, a, b):
        lo, hi = max(a["start"], b["start"]), min(a["end"], b["end"])
        return self.size(lo, hi) if lo < hi else 0

    def core(self, span):
        """Span trimmed of surrounding whitespace, as (start, end)."""
        s, e = span["start"], span["end"]
        while s < e and self.text[s].isspace(): s += 1
        while e > s and self.text[e - 1].isspace(): e -= 1
        return s, e


def prf(tp, n_pred, n_gold):
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "tp": tp, "predicted": n_pred, "gold": n_gold}


def best_match(t, span, candidates):
    scored = [(t.overlap(span, c), -c["start"], c["id"]) for c in candidates]
    best = max(scored, default=(0, 0, None))
    return best[2] if best[0] > 0 else None


def primary_heads(graph):
    return {r["source"]: r for r in graph["relations"] if r["tier"] == "primary"}


def depth(heads, uid):
    d, seen = 0, set()
    while uid in heads and uid not in seen:
        seen.add(uid); uid = heads[uid]["target"]; d += 1
    return d


def exit_edges(pred, groups):
    """For each group of predicted unit ids, the primary edge leaving it (shallowest source)."""
    heads = primary_heads(pred)
    out = {}
    for key, members in groups.items():
        leaving = [heads[u] for u in members if u in heads and heads[u]["target"] not in members]
        if leaving:
            out[key] = min(leaving, key=lambda r: (depth(heads, r["source"]), r["source"]))
    return out


def char_agreement(t, pred_units, gold_spans, attr, default="unannotated"):
    agree = total = 0
    confusion = Counter()
    for u in pred_units:
        for i in range(u["start"], u["end"]):
            if t.text[i].isspace():
                continue
            g = next((s for s in gold_spans if s["start"] <= i < s["end"]), None)
            gv = g[attr] if g else default
            total += 1; agree += (u[attr] == gv); confusion[(gv, u[attr])] += 1
    return agree, total, confusion


def against_gold_graph(text, pred, gold):
    t = Text(text)
    pu, gu = pred["units"], gold["units"]
    cores_p, cores_g = {t.core(u) for u in pu}, {t.core(u) for u in gu}
    ends_p = {e for _, e in cores_p} - {max(e for _, e in cores_p)}
    ends_g = {e for _, e in cores_g} - {max(e for _, e in cores_g)}
    to_gold = {u["id"]: best_match(t, u, gu) for u in pu}
    groups = defaultdict(set)
    for pid, gid in to_gold.items():
        if gid: groups[gid].add(pid)
    exits = exit_edges(pred, groups)
    gheads = primary_heads(gold)
    att = lab = cls = 0
    per_label = Counter()
    for gid, grel in gheads.items():
        prel = exits.get(gid)
        if prel and to_gold.get(prel["target"]) == grel["target"]:
            att += 1
            lab += prel["label"] == grel["label"]
            cls += coarse(prel["label"]) == coarse(grel["label"])
            per_label[(grel["label"], prel["label"])] += 1
    # The root matches when the predicted root covers at least half of the gold root, so a
    # root unit that merely also contains a neighbouring clause is not scored as a miss.
    proot = next(u for u in pu if u["id"] == pred["root"])
    groot = next(u for u in gu if u["id"] == gold["root"])
    root_match = t.overlap(proot, groot) >= 0.5 * t.size(*t.core(groot))
    role_agree, n, role_conf = char_agreement(t, pu, gu, "role")
    stance_agree, _, _ = char_agreement(t, pu, gu, "stance", default="endorsed")
    def derived(g, mapping=None):
        out = set()
        for e in argument_edges(g):
            s, d = (mapping.get(e["source"]), mapping.get(e["target"])) if mapping else (e["source"], e["target"])
            if s and d and s != d:
                out.add((e["type"], s, d))
        return out
    dp, dg = derived(pred, to_gold), derived(gold)
    return {
        "units": {"predicted": len(pu), "gold": len(gu)},
        "segmentation_exact": prf(len(cores_p & cores_g), len(cores_p), len(cores_g)),
        "segmentation_boundaries": prf(len(ends_p & ends_g), len(ends_p), len(ends_g)),
        "role_agreement": round(role_agree / n, 4) if n else None,
        "stance_agreement": round(stance_agree / n, 4) if n else None,
        "root_match": root_match,
        "attachment": {"correct": att, "labelled": lab, "class": cls, "gold_edges": len(gheads),
                       "accuracy": round(att / len(gheads), 4) if gheads else None,
                       "labelled_accuracy": round(lab / len(gheads), 4) if gheads else None,
                       "class_accuracy": round(cls / len(gheads), 4) if gheads else None},
        "derived_edges": prf(len(dp & dg), len(dp), len(dg)),
        "_label_pairs": per_label, "_role_confusion": role_conf,
    }


def against_persuade(text, pred, record):
    t = Text(text)
    gold = [dict(g, id=g["annotation_id"]) for g in record["gold_spans"] or [] if g["role"] != "unannotated"]
    units = sorted(pred["units"], key=lambda u: u["start"])
    agree, n, conf = char_agreement(t, units, gold, "role")
    # Predicted elements: maximal runs of consecutive same-role units (unannotated dropped).
    elements, current = [], None
    for u in units:
        if current and u["role"] == current["role"]:
            current["end"] = u["end"]; current["members"].append(u["id"])
        else:
            current = {"role": u["role"], "start": u["start"], "end": u["end"], "members": [u["id"]]}
            elements.append(current)
    elements = [e for e in elements if e["role"] != "unannotated"]
    roles = sorted({g["role"] for g in gold} | {e["role"] for e in elements})
    per_role, used = {}, set()
    for role in roles:
        ps = [e for e in elements if e["role"] == role]
        gs = [g for g in gold if g["role"] == role]
        tp = 0
        for p in ps:
            for g in gs:
                if g["id"] in used:
                    continue
                ov = t.overlap(p, g)
                if ov >= 0.5 * t.size(g["start"], g["end"]) and ov >= 0.5 * t.size(p["start"], p["end"]):
                    used.add(g["id"]); tp += 1; break
        per_role[role] = prf(tp, len(ps), len(gs))
    scored = [v["f1"] for r, v in per_role.items() if v["gold"]]
    # Attachment of gold elements with a unique hierarchy parent.
    to_elem = {u["id"]: best_match(t, u, gold) for u in units}
    groups = defaultdict(set)
    for pid, gid in to_elem.items():
        if gid: groups[gid].add(pid)
    exits = exit_edges(pred, groups)
    links = [(h["annotation_id"], h["candidate_parent_ids"][0]) for h in record["metadata"].get("hierarchy_candidates", [])
             if h["status"] == "unique_candidate"]
    ids = {g["id"] for g in gold}
    links = [(c, p) for c, p in links if c in ids and p in ids]
    correct = sum(1 for c, p in links if c in exits and to_elem.get(exits[c]["target"]) == p)
    return {"role_agreement": round(agree / n, 4) if n else None,
            "element_f1_macro": round(sum(scored) / len(scored), 4) if scored else None,
            "element_f1_by_role": per_role,
            "attachment": {"correct": correct, "gold_links": len(links),
                           "accuracy": round(correct / len(links), 4) if links else None},
            "_role_confusion": conf}


def summarise(per_essay, key):
    rows = [v[key] for v in per_essay.values() if key in v]
    if not rows:
        return None
    if key == "gold_graph":
        tot = lambda path: sum(r[path[0]][path[1]] for r in rows)
        seg = prf(tot(("segmentation_exact", "tp")), tot(("segmentation_exact", "predicted")), tot(("segmentation_exact", "gold")))
        bnd = prf(tot(("segmentation_boundaries", "tp")), tot(("segmentation_boundaries", "predicted")), tot(("segmentation_boundaries", "gold")))
        edges = tot(("attachment", "gold_edges"))
        der = prf(tot(("derived_edges", "tp")), tot(("derived_edges", "predicted")), tot(("derived_edges", "gold")))
        labels = sum((r["_label_pairs"] for r in rows), Counter())
        return {"essays": len(rows), "segmentation_exact": seg, "segmentation_boundaries": bnd,
                "root_match": f"{sum(r['root_match'] for r in rows)}/{len(rows)}",
                "attachment_accuracy": round(tot(("attachment", "correct")) / edges, 4),
                "labelled_accuracy": round(tot(("attachment", "labelled")) / edges, 4),
                "class_accuracy": round(tot(("attachment", "class")) / edges, 4),
                "role_agreement_mean": round(sum(r["role_agreement"] for r in rows) / len(rows), 4),
                "stance_agreement_mean": round(sum(r["stance_agreement"] for r in rows) / len(rows), 4),
                "derived_edges": der,
                "label_confusions_on_correct_attachments": [
                    {"gold": g, "predicted": p, "count": c} for (g, p), c in labels.most_common() if g != p]}
    links = sum(r["attachment"]["gold_links"] for r in rows)
    confusion = sum((r["_role_confusion"] for r in rows), Counter())
    return {"essays": len(rows),
            "role_agreement_mean": round(sum(r["role_agreement"] for r in rows) / len(rows), 4),
            "element_f1_macro_mean": round(sum(r["element_f1_macro"] for r in rows) / len(rows), 4),
            "attachment_accuracy": round(sum(r["attachment"]["correct"] for r in rows) / links, 4) if links else None,
            "role_confusion_chars": [{"gold": g, "predicted": p, "chars": c} for (g, p), c in confusion.most_common() if g != p][:15]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--gold-dir", type=Path, default=Path("data/annotations/argument_graphs"))
    args = parser.parse_args()
    with args.records.open() as handle:
        records = {r["example_id"]: r for r in map(json.loads, handle)}
    per_essay = {}
    for path in sorted(args.run_dir.glob("*.graph.json")):
        pred = json.loads(path.read_text())
        rec = records[pred["example_id"]]
        entry = {"persuade": against_persuade(rec["response_text"], pred, rec)}
        gold_path = args.gold_dir / path.name.replace(".graph.json", ".json")
        if gold_path.exists():
            entry["gold_graph"] = against_gold_graph(rec["response_text"], pred, json.loads(gold_path.read_text()))
        per_essay[pred["example_id"]] = entry
    manifest = json.loads((args.run_dir / "manifest.json").read_text())
    failed = {e: s["status"] for e, s in manifest["essays"].items() if s["status"] != "ok"}
    report = {"run": manifest["config_hash"], "model": manifest["model"], "effort": manifest["effort"],
              "extracted": len(per_essay), "failed": failed,
              "tokens": {"input": sum(s["input_tokens"] for s in manifest["essays"].values()),
                         "output": sum(s["output_tokens"] for s in manifest["essays"].values())},
              "summary": {"gold_graphs": summarise(per_essay, "gold_graph"), "persuade": summarise(per_essay, "persuade")},
              "per_essay": {e: {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in entry.items()}
                            for e, entry in per_essay.items()}}
    (args.run_dir / "metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
