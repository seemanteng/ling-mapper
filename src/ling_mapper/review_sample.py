"""Write stratified CSV sheets for manual review of recovered spans and hierarchy links."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

SEARCH = ("unique_exact", "unique_trimmed", "unique_whitespace_normalised")
# (stratum, quota; None = all rows)
STRATA = [
    ("search_short", 40), ("search_other", 20), ("offset_trimmed", 40), ("sequence_unique", 15),
    ("nearest_clear", None), ("offset_exact_control", 10), ("sequence_conflict", None),
    ("kept_order_swap", None),
]
SPAN_VERDICTS = "correct | wrong_location | wrong_boundary | wrong_role | unsure"
LINK_VERDICTS = "supports | elaborates | same_thread | attacks_or_rebuts | wrong_parent | unsure"
CONTEXT = 150


def rank(seed, key):
    return hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()


def stratum(method, span_len, swapped):
    if swapped:
        return "kept_order_swap"
    if method in SEARCH:
        return "search_short" if span_len < 30 else "search_other"
    if method in ("raw_exact", "inclusive_exact"):
        return "offset_exact_control"
    return method


def span_row(text, rec, aid, role, method, raw, start, end, group):
    try:
        a, b = int(raw["discourse_start"]), int(raw["discourse_end"])
        at_offsets = text[max(a, 0):b + 1]
    except ValueError:
        a = b = at_offsets = ""
    return {
        "stratum": group, "example_id": rec["example_id"], "annotation_id": aid,
        "role": role, "method": method, "supplied_start": a, "supplied_end": b,
        "recovered_start": start, "recovered_end": end,
        "start_delta": "" if start is None or a == "" else start - a,
        "annotation_text": raw["discourse_text"],
        "context_before": "" if start is None else text[max(0, start - CONTEXT):start],
        "recovered_text": "" if start is None else text[start:end],
        "context_after": "" if start is None else text[end:end + CONTEXT],
        "text_at_supplied_offsets": at_offsets,
        "verdict": "", "notes": "",
    }


def build(records, seed):
    pools = {name: [] for name, _ in STRATA}
    links = []
    for rec in records:
        text = rec["response_text"]
        spans = rec["gold_spans"] or []
        starts = [g["start"] for g in spans]
        swapped = {i for i in range(len(spans) - 1) if starts[i] >= starts[i + 1]}
        swapped |= {i + 1 for i in swapped}
        for i, g in enumerate(spans):
            prov = g["provenance"]
            group = stratum(prov["recovery_method"], g["end"] - g["start"], i in swapped)
            if group in pools:
                pools[group].append(span_row(text, rec, g["annotation_id"], g["original_label"],
                                             prov["recovery_method"], prov["raw"], g["start"], g["end"], group))
        for u in rec["metadata"]["unresolved_annotations"]:
            if u["reason"] != "sequence_conflict":
                continue
            prov = u["provenance"]
            start, end, method = prov["disambiguation"]["rejected"]
            row = span_row(text, rec, u["annotation_id"], prov["raw"]["discourse_type"],
                           f"rejected:{method}", prov["raw"], start, end, "sequence_conflict")
            row["verdict_options"] = "rejection_correct | rejection_wrong | unsure"
            pools["sequence_conflict"].append(row)
        by_id = {g["annotation_id"]: g for g in spans}
        for h in rec["metadata"]["hierarchy_candidates"]:
            if h["status"] != "unique_candidate":
                continue
            child, parent = by_id.get(h["annotation_id"]), by_id.get(h["candidate_parent_ids"][0])
            if child and parent:
                links.append({
                    "example_id": rec["example_id"], "child_id": child["annotation_id"],
                    "child_role": child["original_label"], "child_text": child["text"],
                    "parent_role": parent["original_label"], "parent_text": parent["text"],
                    "child_before_parent": child["start"] < parent["start"],
                    "essay_text": text, "verdict": "", "notes": "",
                })
    rows = []
    for name, quota in STRATA:
        pool = sorted(pools[name], key=lambda r: rank(seed, r["annotation_id"]))
        rows.extend(pool if quota is None else pool[:quota])
    links.sort(key=lambda r: rank(seed, r["child_id"]))
    return rows, links


def write_csv(path, rows, verdicts):
    fields = list(dict.fromkeys(k for r in rows for k in r)) + ["verdict_options"]
    fields = list(dict.fromkeys(fields))
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({"verdict_options": verdicts, **r})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--links", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    with args.records.open() as handle:
        records = [json.loads(line) for line in handle]
    rows, links = build(records, args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    spans_path = args.output_dir / "span_review.csv"
    links_path = args.output_dir / "hierarchy_review.csv"
    if spans_path.exists() or links_path.exists():
        parser.error("Review sheets already exist; refusing to overwrite recorded verdicts")
    write_csv(spans_path, rows, SPAN_VERDICTS)
    write_csv(links_path, links[:args.links], LINK_VERDICTS)
    counts = {}
    for r in rows:
        counts[r["stratum"]] = counts.get(r["stratum"], 0) + 1
    print(json.dumps({"span_rows": len(rows), "by_stratum": counts,
                      "hierarchy_rows": min(args.links, len(links))}, indent=2))


if __name__ == "__main__":
    main()
