"""Import PERSUADE essays and discourse annotations into the common contract."""
import csv
import hashlib
import json
import re
import math
from collections import Counter, defaultdict
from pathlib import Path

from ..schemas import ExampleRecord, GoldSpan
from ..spans import recover_sequence, displacement

ROLES = {
    "Lead": "lead", "Position": "position", "Claim": "claim",
    "Counterclaim": "counterclaim", "Rebuttal": "rebuttal", "Evidence": "evidence",
    "Concluding Statement": "concluding_summary", "Concluding Summary": "concluding_summary",
    "Unannotated": "unannotated",
}
RAW_FIELDS = (
    "discourse_id", "discourse_start", "discourse_end", "discourse_text",
    "discourse_type", "discourse_type_num", "discourse_effectiveness",
    "hierarchical_id", "hierarchical_text", "hierarchical_label",
)


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_persuade(path, *, holistic_path=None, prompt_name=None):
    """Return records and audit report. Unresolved rows remain in record metadata.

    The annotation file is authoritative for its essays. A supplemental holistic
    file is checked, not used to overwrite text. Supports holistic-only inputs.
    """
    path = Path(path)
    csv.field_size_limit(10_000_000)
    digest = file_hash(path)
    essays, annotations = {}, defaultdict(list)
    raw_ids = Counter()
    id_texts = defaultdict(set)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        required = {"essay_id_comp", "full_text", "assignment", "prompt_name"}
        if not required <= columns:
            raise ValueError(f"Missing columns: {sorted(required - columns)}")
        has_annotations = "discourse_type" in columns
        if has_annotations and not set(RAW_FIELDS[:5]) <= columns:
            raise ValueError("Incomplete discourse annotation columns")
        for line, row in enumerate(reader, 2):
            if prompt_name is not None and row["prompt_name"] != prompt_name:
                continue
            eid = row["essay_id_comp"]
            if not eid:
                raise ValueError(f"Empty essay ID at CSV record {line}")
            text_hash = hashlib.sha256(row['full_text'].encode()).hexdigest()
            id_texts[eid].add(text_hash)
            suspicious = bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?[Ee][+-]\d+", eid))
            if len(id_texts[eid]) > 1 and not suspicious:
                raise ValueError(f"Conflicting full_text values for essay ID {eid}")
            group_id = (eid, text_hash)
            if group_id not in essays:
                essays[group_id] = {k: row.get(k, "") for k in (
                    "full_text", "assignment", "prompt_name", "source_text",
                    "competition_set", "holistic_essay_score",
                )}
            elif any(essays[group_id][k] != row.get(k, "") for k in essays[group_id]):
                raise ValueError(f"Conflicting essay metadata for {eid}")
            if has_annotations:
                annotations[group_id].append({**{k: row.get(k, "") for k in RAW_FIELDS}, "csv_record": line})
                raw_ids[row["discourse_id"]] += 1
    if not essays:
        raise ValueError("No essays matched input/filter")
    supplementary, by_text = defaultdict(set), defaultdict(set)
    if holistic_path:
        with open(holistic_path, newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                sid, text = row['essay_id_comp'], row['full_text']
                supplementary[sid].add(text)
                by_text[text].add(sid)

    methods, reasons = Counter(), Counter()
    by_role, by_prompt = defaultdict(Counter), defaultdict(Counter)
    records, missing_joins, different_text, raw_oob = [], [], [], 0
    hierarchy_counts = Counter()
    join_counts = Counter()
    displacement_rows = []
    for group_id in sorted(essays):
        eid, text_hash = group_id
        essay = essays[group_id]
        text = essay["full_text"]
        join_status, canonical_id = 'not_checked', None
        if holistic_path:
            if text in supplementary.get(eid, set()):
                join_status, canonical_id = 'id_and_text', eid
            else:
                if eid in supplementary:
                    different_text.append(eid)
                matches = sorted(by_text.get(text, set()))
                if len(matches) == 1:
                    join_status, canonical_id = 'unique_exact_text', matches[0]
                elif matches:
                    join_status = 'ambiguous_exact_text'
                else:
                    join_status = 'unmatched'
                    missing_joins.append(eid)
        join_counts[join_status] += 1
        affected = bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?[Ee][+-]\d+", eid)) or len(id_texts[eid]) > 1 or join_status == 'unique_exact_text' or len(supplementary.get(eid, set())) > 1
        example_id = f"persuade:text:{text_hash}" if affected else f"persuade:{eid}"
        recoveries, decisions = recover_sequence(text, annotations[group_id])
        # Source gap rows can be word fragments inside a labelled span; drop those.
        labelled = [(r.start, r.end) for row, r in zip(annotations[group_id], recoveries)
                    if row["discourse_type"] != "Unannotated" and r.start is not None and r.reason is None]
        gold, unresolved, entries, seen = [], [], [], set()
        for row, recovered, decision in zip(annotations[group_id], recoveries, decisions):
            label = row["discourse_type"]
            key = json.dumps([example_id, row["discourse_start"], row["discourse_end"], label], ensure_ascii=False)
            aid = "persuade-span:" + hashlib.sha256(key.encode()).hexdigest()[:24]
            if aid in seen:
                raise ValueError(f"Duplicate essay/span/role key in {eid}")
            seen.add(aid)
            try:
                a, b = int(row["discourse_start"]), int(row["discourse_end"])
                if not 0 <= a <= b <= len(text):
                    raw_oob += 1
            except ValueError:
                raw_oob += 1
            reason = "unknown_role" if label not in ROLES else recovered.reason
            if (reason is None and label == "Unannotated" and recovered.start is not None
                    and any(s < recovered.end and recovered.start < e for s, e in labelled)):
                reason = "unannotated_overlaps_labelled"
            accepted = recovered.start is not None and reason is None
            method = recovered.method if accepted else "unresolved"
            methods[method] += 1
            for counter in (by_role[label], by_prompt[essay["prompt_name"]]):
                counter["total"] += 1
                counter["recovered" if accepted else "unresolved"] += 1
            provenance = {"file_sha256": digest, "raw": row, "recovery_method": method,
                          "review_status": "not_human_reviewed", "disambiguation": decision,
                          "displacement": displacement(recovered, row)}
            if accepted and provenance['displacement'] is not None:
                displacement_rows.append({'example_id': example_id, 'annotation_id': aid,
                    'role': label, 'method': method, **provenance['displacement']})
            if accepted:
                gold.append(GoldSpan(aid, example_id, recovered.start, recovered.end,
                                     text[recovered.start:recovered.end], label, ROLES[label],
                                     provenance=provenance))
            else:
                reasons[reason or "unknown"] += 1
                unresolved.append({"annotation_id": aid, "reason": reason, "provenance": provenance})
            entries.append((aid, row, accepted))
        # Preserve candidate parent information without asserting edge semantics.
        hierarchy = []
        for aid, row, accepted in entries:
            if not any(row[k] for k in ("hierarchical_id", "hierarchical_text", "hierarchical_label")):
                continue
            candidates = [other_id for other_id, other, ok in entries
                          if other_id != aid and other["discourse_type"] == row["hierarchical_label"]
                          and other["discourse_text"].strip() == row["hierarchical_text"].strip()]
            status = "unique_candidate" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched"
            hierarchy_counts[status] += 1
            hierarchy.append({"annotation_id": aid, "candidate_parent_ids": candidates,
                              "status": status, "semantics": "unverified"})
        metadata = {
            "dataset": "PERSUADE 2.0", "original_id": eid,
            "identity_method": "text_sha256" if affected else "original_id",
            "text_sha256": text_hash, "canonical_essay_id": canonical_id,
            "supplementary_join_status": join_status,
            "prompt_group": essay["prompt_name"], "source_citations": essay["source_text"],
            "official_split": essay["competition_set"] or None,
            "holistic_score": essay["holistic_essay_score"] or None,
            "source_file": path.name, "file_sha256": digest,
            "annotation_status": "available" if has_annotations else "unavailable",
            "unresolved_annotations": unresolved, "hierarchy_candidates": hierarchy,
        }
        record = ExampleRecord(example_id, essay["assignment"], text,
                               gold_spans=gold if has_annotations else None, metadata=metadata)
        record.validate()
        records.append(record)
    def distribution(values):
        values = sorted(values)
        if not values:
            return {'count': 0}
        return {'count': len(values), **{name: values[min(len(values)-1, math.ceil(q*len(values))-1)]
                for name, q in [('p50', .5), ('p90', .9), ('p95', .95), ('p99', .99), ('max', 1)]}}
    if len({r.example_id for r in records}) != len(records):
        raise ValueError('Duplicate derived example IDs; inspect raw aliases before merging')
    report = {
        "id_to_text_check": "checked_all_selected_rows",
        "raw_essay_id_collisions": {k: len(v) for k, v in id_texts.items() if len(v)>1},
        "supplementary_join_methods": dict(join_counts),
        "supplementary_id_text_collisions": {k: len(v) for k, v in supplementary.items() if len(v)>1},
        "disambiguation_policy": {'min_margin': 20, 'distance_ratio': 2.0, 'max_distance': 100,
                                   'anchors': 'independent_recoveries_only',
                                   'order_check': 'searched matches outside every longest increasing chain -> sequence_conflict'},
        "displacement": {
            'absolute_start': distribution([x['absolute_start_delta'] for x in displacement_rows]),
            'max_absolute_boundary': distribution([x['max_absolute_delta'] for x in displacement_rows]),
            'by_method': {m: distribution([x['absolute_start_delta'] for x in displacement_rows if x['method']==m]) for m in methods if m!='unresolved'},
            'largest_50': sorted(displacement_rows, key=lambda x: (-x['max_absolute_delta'], x['annotation_id']))[:50]},
        "source_file": str(path), "file_sha256": digest, "prompt_filter": prompt_name,
        "essays": len(records), "annotation_rows": sum(methods.values()),
        "recovery_methods": dict(methods), "unresolved_reasons": dict(reasons),
        "by_role": {k: dict(v) for k, v in by_role.items()},
        "by_prompt": {k: dict(v) for k, v in by_prompt.items()},
        "raw_bounds_invalid": raw_oob, "unique_raw_discourse_ids": len(raw_ids),
        "repeated_raw_discourse_id_values": sum(n > 1 for n in raw_ids.values()),
        "supplementary_join_checked": holistic_path is not None,
        "missing_supplementary_essay_ids": missing_joins,
        "different_supplementary_text_ids": different_text,
        "hierarchy_candidates": dict(hierarchy_counts),
        "gold_relations_status": "not_imported_semantics_unverified",
        "review_status": "automated_recovery_requires_sample_review",
    }
    return records, report
