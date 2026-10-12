"""Compare extraction runs against the reference graphs: per-class role and stance scores, headline
metrics with bootstrap intervals over essays, and paired differences between runs.

All scores come from the same code as `evaluate.py` (`against_gold_graph`, `char_agreement`), so they
match `metrics.json`. An essay without a valid graph counts as zeros, not as missing, so a model that
fails is not rewarded for it. Intervals resample essays with replacement (same resamples for every
run, so differences are paired). With 30 essays from one prompt they are wide; read them as the size of
the noise, not as a significance test across prompts.
"""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from .evaluate import Text, against_gold_graph, char_agreement

HEADLINES = ("root", "attachment", "labelled_attachment", "class_attachment", "role_agreement", "stance_agreement",
             "derived_edges_f1", "segmentation_f1")


def essay_stats(text, pred, gold):
    """Per-essay counts. `pred` None (no valid graph) scores zero on every metric."""
    t = Text(text)
    edges = sum(1 for r in gold["relations"] if r["tier"] == "primary")
    if pred is None:
        return {"edges": edges, "att": 0, "lab": 0, "cls": 0, "root": 0, "role": 0.0, "stance": 0.0,
                "dtp": 0, "dpred": 0, "dgold": 0, "stp": 0, "spred": 0, "sgold": len(gold["units"]),
                "role_conf": Counter(), "stance_conf": Counter()}
    s = against_gold_graph(text, pred, gold)
    _, _, role_conf = char_agreement(t, pred["units"], gold["units"], "role")
    _, _, stance_conf = char_agreement(t, pred["units"], gold["units"], "stance", default="endorsed")
    return {"edges": edges, "att": s["attachment"]["correct"], "lab": s["attachment"]["labelled"],
            "cls": s["attachment"]["class"], "root": int(s["root_match"]), "role": s["role_agreement"],
            "stance": s["stance_agreement"], "dtp": s["derived_edges"]["tp"], "dpred": s["derived_edges"]["predicted"],
            "dgold": s["derived_edges"]["gold"], "stp": s["segmentation_exact"]["tp"],
            "spred": s["segmentation_exact"]["predicted"], "sgold": s["segmentation_exact"]["gold"],
            "role_conf": role_conf, "stance_conf": stance_conf}


def f1(tp, pred, gold):
    p, r = (tp / pred if pred else 0.0), (tp / gold if gold else 0.0)
    return 2 * p * r / (p + r) if p + r else 0.0


def headlines(rows):
    """Headline metrics over a list of per-essay stats (pooled counts, as in evaluate.py)."""
    n, edges = len(rows), sum(r["edges"] for r in rows)
    total = lambda k: sum(r[k] for r in rows)
    return {"root": total("root") / n, "attachment": total("att") / edges, "labelled_attachment": total("lab") / edges,
            "class_attachment": total("cls") / edges, "role_agreement": total("role") / n,
            "stance_agreement": total("stance") / n,
            "derived_edges_f1": f1(total("dtp"), total("dpred"), total("dgold")),
            "segmentation_f1": f1(total("stp"), total("spred"), total("sgold"))}


def class_scores(rows, key):
    """Per-class precision/recall/F1 from character confusions pooled over essays, plus macro-F1
    over the classes that occur in the reference."""
    conf = sum((r[key] for r in rows), Counter())
    classes = sorted({g for g, _ in conf} | {p for _, p in conf})
    out = {}
    for c in classes:
        tp = conf[(c, c)]
        gold, pred = sum(v for (g, _), v in conf.items() if g == c), sum(v for (_, p), v in conf.items() if p == c)
        out[c] = {"precision": tp / pred if pred else 0.0, "recall": tp / gold if gold else 0.0,
                  "f1": f1(tp, pred, gold), "gold_chars": gold}
    scored = [v["f1"] for v in out.values() if v["gold_chars"]]
    return out, (sum(scored) / len(scored) if scored else 0.0)


def bootstrap(runs, samples=2000, seed=0):
    """runs: {name: [per-essay stats in the same essay order]}. Returns (intervals, paired differences)."""
    rng = random.Random(seed)
    names = list(runs)
    n = len(next(iter(runs.values())))
    draws = {name: {k: [] for k in HEADLINES} for name in names}
    for _ in range(samples):
        idx = [rng.randrange(n) for _ in range(n)]
        for name in names:
            h = headlines([runs[name][i] for i in idx])
            for k in HEADLINES:
                draws[name][k].append(h[k])
    pct = lambda xs, q: sorted(xs)[min(len(xs) - 1, int(q * len(xs)))]
    intervals = {name: {k: (pct(v, 0.025), pct(v, 0.975)) for k, v in d.items()} for name, d in draws.items()}
    diffs = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            diffs[(a, b)] = {}
            for k in HEADLINES:
                d = [x - y for x, y in zip(draws[a][k], draws[b][k])]
                diffs[(a, b)][k] = (pct(d, 0.025), pct(d, 0.975))
    return intervals, diffs


def load_run(run_dir, records, gold_dir):
    rows = []
    for gold_path in sorted(Path(gold_dir).glob("*.json")):
        gold = json.loads(gold_path.read_text())
        text = records[gold["example_id"]]["response_text"]
        graph_path = Path(run_dir) / f"{gold_path.stem}.graph.json"
        pred = json.loads(graph_path.read_text()) if graph_path.exists() else None
        rows.append(essay_stats(text, pred, gold))
    return rows


def report(runs, reference_counts, reference=None):
    """Markdown report for {name: per-essay stats}. With `reference`, paired differences are only
    those between that run and each other run (first minus reference)."""
    out = ["# Run comparison against the self-annotated reference graphs", ""]
    head = {n: headlines(r) for n, r in runs.items()}
    ci, diffs = bootstrap(runs)
    names = list(runs)
    out += ["## Headline metrics (95% bootstrap interval over essays)", "",
            "| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k in HEADLINES:
        out.append(f"| {k} | " + " | ".join(f"{head[n][k]:.3f} ({ci[n][k][0]:.2f}–{ci[n][k][1]:.2f})" for n in names) + " |")
    for title, key, ref in (("Role", "role_conf", "roles"), ("Stance", "stance_conf", "stances")):
        scores = {n: class_scores(r, key) for n, r in runs.items()}
        classes = sorted({c for s, _ in scores.values() for c in s})
        out += ["", f"## {title}: per-class F1 (precision / recall), character-level", "",
                "| Class | Reference units | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
        for c in classes:
            cells = []
            for n in names:
                v = scores[n][0].get(c)
                cells.append(f"{v['f1']:.2f} ({v['precision']:.2f} / {v['recall']:.2f})" if v and v["gold_chars"] else "n/a" if not v else f"0.00 ({v['precision']:.2f} / 0.00)")
            out.append(f"| {c} | {reference_counts[ref].get(c, 0)} | " + " | ".join(cells) + " |")
        out.append("| **macro-F1** | | " + " | ".join(f"**{scores[n][1]:.3f}**" for n in names) + " |")
    out += ["", "## Paired differences (first minus second, 95% interval; excludes 0 = consistent in these 30 essays)", ""]
    shown = ("root", "attachment", "labelled_attachment", "role_agreement", "derived_edges_f1")
    out += ["| Pair | " + " | ".join(shown) + " |", "|---|" + "---|" * len(shown)]
    for (a, b), d in diffs.items():
        if reference and reference not in (a, b):
            continue
        if reference and b == reference:
            a, b, d = b, a, {k: (-hi, -lo) for k, (lo, hi) in d.items()}
        cells = []
        for k in shown:
            lo, hi = d[k]
            mid = head[a][k] - head[b][k]
            cells.append(f"{mid:+.3f} ({lo:+.2f}, {hi:+.2f}){' *' if lo > 0 or hi < 0 else ''}")
        out.append(f"| {a} − {b} | " + " | ".join(cells) + " |")
    out += ["", "`*` marks an interval that excludes 0. Class scores pool characters over essays, so long essays weigh more;",
            "stance classes other than Endorsed have very few reference units, so read those rows as indicative."]
    return "\n".join(out) + "\n"


def reference_counts(gold_dir):
    roles, stances = Counter(), Counter()
    for path in Path(gold_dir).glob("*.json"):
        for u in json.loads(path.read_text())["units"]:
            roles[u["role"]] += 1
            stances[u["stance"]] += 1
    return {"roles": roles, "stances": stances}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--gold-dir", type=Path, required=True)
    parser.add_argument("--run", action="append", required=True, metavar="NAME=DIR", help="Repeatable")
    parser.add_argument("--output", type=Path, required=True, help="Markdown report to write")
    parser.add_argument("--reference", help="Run name; show paired differences only against this run (it comes first in each pair)")
    args = parser.parse_args()
    with args.records.open() as handle:
        records = {r["example_id"]: r for r in map(json.loads, handle)}
    runs = {}
    for spec in args.run:
        name, directory = spec.split("=", 1)
        runs[name] = load_run(directory, records, args.gold_dir)
    args.output.write_text(report(runs, reference_counts(args.gold_dir), args.reference))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
