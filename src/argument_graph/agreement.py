"""Self-agreement check: re-label a few essays from blank sheets and compare with the final labels.

`sheets` picks essays (one per score band by default, seeded) and writes blank copies of their
final sheets: the same segments, with every label column empty. The segmentation is kept so that
the comparison is about labels only. The author fills them in after a delay, without looking at the
final sheets, and `score` then compares the two:

- agreement and Cohen's kappa for role, stance and relation label, and raw agreement for the parent;
- the same graph metrics the models are scored with (`compare.headlines`, per-class scores), with the
  new labels as the "prediction" and the final labels as the reference. That gives a human ceiling on
  the model scale: a model cannot be expected to agree with the reference more than the author does.

This measures one person's consistency over time, not agreement between people.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from .compare import class_scores, essay_stats, headlines
from .graph_schema import validate_graph
from .reference_graph import COLUMNS, read_sheet, to_graph
from .select_batch import seeded_key
from .presegment import SHEET_COLUMNS

LABEL_COLUMNS = [COLUMNS["role"], COLUMNS["stance"], COLUMNS["parent"], COLUMNS["how"], "Notes"]


def sheet_path(directory, essay_no):
    return Path(directory) / f"Essay {essay_no}.csv"


def choose_essays(sheets_dir, records, seed=42, per_band=1, min_segments=15, max_segments=40):
    """Seeded choice of `per_band` essays per holistic score band with a manageable length."""
    by_band = {}
    for path in Path(sheets_dir).glob("Essay *.csv"):
        rows = read_sheet(path)
        example_id = f"persuade:{rows[0]['example_id']}"
        if min_segments <= len(rows) <= max_segments:
            band = records[example_id]["metadata"]["holistic_score"]
            by_band.setdefault(band, []).append((seeded_key(seed, example_id), int(rows[0]["essay_no"]), example_id, len(rows)))
    chosen = []
    for band in sorted(by_band):
        chosen += [(band, no, eid, n) for _, no, eid, n in sorted(by_band[band])[:per_band]]
    return chosen


def write_blank_sheets(sheets_dir, out_dir, essay_numbers, records):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for no in essay_numbers:
        rows = read_sheet(sheet_path(sheets_dir, no))
        text = records[f"persuade:{rows[0]['example_id']}"]["response_text"]
        (out_dir / f"Essay {no}.txt").write_text(text + "\n", encoding="utf-8")
        with sheet_path(out_dir, no).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(SHEET_COLUMNS)
            for r in rows:
                writer.writerow([r["essay_no"], r["example_id"], r["segment_no"], r["unit_id"], r["segment_text"], "", "", "", "", ""])
            writer.writerow([""] * len(SHEET_COLUMNS))
            writer.writerow(["", "Overall Essay Comments: "] + [""] * (len(SHEET_COLUMNS) - 2))
            writer.writerow(["", "[Write here]"] + [""] * (len(SHEET_COLUMNS) - 2))


def cohen_kappa(pairs):
    """Cohen's kappa for a list of (label_a, label_b); 1.0 when both raters use one identical label."""
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    a_counts, b_counts = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(a_counts[c] * b_counts[c] for c in a_counts) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def field_agreement(final_rows, new_rows):
    """Per-field raw agreement and kappa over rows paired by unit id."""
    new_by_id = {r["unit_id"]: r for r in new_rows}
    out = {}
    for name, column in (("role", COLUMNS["role"]), ("stance", COLUMNS["stance"]), ("relation", COLUMNS["how"]),
                         ("parent", COLUMNS["parent"])):
        pairs = [(r[column].strip(), new_by_id[r["unit_id"]][column].strip()) for r in final_rows]
        out[name] = pairs
    return out


def score(final_dir, relabel_dir, records):
    """Returns (markdown report, per-essay problems)."""
    essays, problems, stats, pooled = [], {}, [], {k: [] for k in ("role", "stance", "relation", "parent")}
    for path in sorted(Path(relabel_dir).glob("Essay *.csv"), key=lambda p: int(p.stem.split()[-1])):
        no = int(path.stem.split()[-1])
        final_rows, new_rows = read_sheet(sheet_path(final_dir, no)), read_sheet(path)
        example_id = f"persuade:{final_rows[0]['example_id']}"
        text = records[example_id]["response_text"]
        if [r["segment_text"] for r in final_rows] != [r["segment_text"] for r in new_rows]:
            problems[no] = ["segments differ from the final sheet; do not edit the segment text"]
            continue
        if any(not r[COLUMNS["role"]].strip() for r in new_rows):
            problems[no] = ["some segments have no role yet (sheet not finished)"]
            continue
        try:
            new_graph = to_graph(example_id, text, new_rows)
        except (ValueError, KeyError) as err:
            problems[no] = [f"cannot convert the new sheet: {err!r}"]
            continue
        errors = validate_graph(new_graph, text)
        if errors:
            problems[no] = errors
            continue
        final_graph = to_graph(example_id, text, final_rows)
        stats.append(essay_stats(text, new_graph, final_graph))
        fields = field_agreement(final_rows, new_rows)
        for k in pooled:
            pooled[k] += fields[k]
        essays.append(no)
    return report(essays, stats, pooled, problems), problems


def report(essays, stats, pooled, problems):
    out = ["# Self-agreement: re-labelled essays against the final labels", ""]
    if problems:
        out += ["## Not scored", ""] + [f"- Essay {no}: {'; '.join(errs[:3])}" for no, errs in sorted(problems.items())] + [""]
    if not stats:
        return "\n".join(out + ["No finished essays to score yet.", ""])
    out += [f"Essays scored: {', '.join(map(str, essays))} ({len(pooled['role'])} segments)", "",
            "## Label agreement (same segments, labels only)", "", "| Field | Raw agreement | Cohen's kappa |", "|---|---|---|"]
    for name, pairs in pooled.items():
        raw = sum(a == b for a, b in pairs) / len(pairs)
        kappa = cohen_kappa(pairs) if name != "parent" else None
        out.append(f"| {name} | {raw:.3f} | {'n/a (many categories)' if kappa is None else f'{kappa:.3f}'} |")
    h = headlines(stats)
    out += ["", "## Human ceiling on the model metrics (new labels scored against the final labels)", "",
            "| Metric | Self-agreement |", "|---|---|"]
    out += [f"| {k} | {v:.3f} |" for k, v in h.items() if k != "segmentation_f1"]
    for title, key in (("Role", "role_conf"), ("Stance", "stance_conf")):
        scores, macro = class_scores(stats, key)
        out += ["", f"## {title}: per-class F1 (precision / recall)", "", "| Class | F1 (P / R) | Reference chars |", "|---|---|---|"]
        out += [f"| {c} | {v['f1']:.2f} ({v['precision']:.2f} / {v['recall']:.2f}) | {v['gold_chars']} |"
                for c, v in scores.items() if v["gold_chars"]]
        out.append(f"| **macro-F1** | **{macro:.3f}** | |")
    out += ["", "Few essays and few minority-class segments: read the stance rows as indicative. Segmentation is fixed by design,",
            "so it is not scored. This is one person's consistency over time, not agreement between annotators."]
    return "\n".join(out) + "\n"


def load_records(path):
    with Path(path).open() as handle:
        return {r["example_id"]: r for r in map(json.loads, handle)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sheets", "score"):
        p = sub.add_parser(name)
        p.add_argument("--records", type=Path, default=Path("data/processed/distance_learning_v3/records.jsonl"))
        p.add_argument("--final-dir", type=Path, default=Path("data/annotations/self_annotation_online_learning_30"))
    sub.choices["sheets"].add_argument("--output-dir", type=Path, required=True)
    sub.choices["sheets"].add_argument("--seed", type=int, default=42)
    sub.choices["sheets"].add_argument("--per-band", type=int, default=1)
    sub.choices["score"].add_argument("--relabel-dir", type=Path, required=True)
    sub.choices["score"].add_argument("--output", type=Path)
    args = parser.parse_args()
    records = load_records(args.records)
    if args.command == "sheets":
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            parser.error("Output directory must be empty")
        chosen = choose_essays(args.final_dir, records, args.seed, args.per_band)
        write_blank_sheets(args.final_dir, args.output_dir, [no for _, no, _, _ in chosen], records)
        (args.output_dir / "selection.json").write_text(json.dumps(
            {"seed": args.seed, "per_band": args.per_band,
             "essays": [{"essay_no": no, "example_id": eid, "holistic_score": band, "segments": n} for band, no, eid, n in chosen]}, indent=2))
        for band, no, eid, n in chosen:
            print(f"Essay {no}: score {band}, {n} segments")
    else:
        text, problems = score(args.final_dir, args.relabel_dir, records)
        (args.output.write_text(text) if args.output else print(text))


if __name__ == "__main__":
    main()
