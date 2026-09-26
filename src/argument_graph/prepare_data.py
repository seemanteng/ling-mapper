"""CLI for reproducible import and essay-level pilot selection."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .loaders.persuade import load_persuade


def select_pilot(records, size, seed, inspected=()):
    """Deterministic score-band pilot split.

    `inspected` lists essays already examined while designing the method. Any of
    them drawn for pilot_check moves to development and is replaced by the next
    unselected essay of the same score band in the same seeded order, so the
    held-out check stays unseen and band-balanced.
    """
    groups = defaultdict(list)
    for record in records:
        if record.metadata.get("official_split") != "train":
            continue
        groups[record.metadata.get("holistic_score") or "unknown"].append(record)
    for group in groups.values():
        group.sort(key=lambda r: hashlib.sha256(f"{seed}:{r.example_id}".encode()).hexdigest())
    selected = []
    while len(selected) < size and any(groups.values()):
        for score in sorted(groups):
            if groups[score] and len(selected) < size:
                selected.append(groups[score].pop())
    if len(selected) != size:
        raise ValueError(f"Need {size} official training essays; found {len(selected)}")
    # Split each score band alternately, balancing total partition sizes.
    development, check = [], []
    bands = defaultdict(list)
    for record in selected:
        bands[record.metadata.get("holistic_score")].append(record)
    for score in sorted(bands, key=str):
        for record in bands[score]:
            (development if len(development) <= len(check) else check).append(record.example_id)
    band_of = {r.example_id: r.metadata.get("holistic_score") or "unknown" for r in selected}
    replacements = {}
    for example_id in inspected:
        if example_id not in check:
            continue
        band = band_of[example_id]
        if not groups[band]:
            raise ValueError(f"No unselected essay left in score band {band} to replace {example_id}")
        replacement = groups[band].pop()
        selected.append(replacement)
        check[check.index(example_id)] = replacement.example_id
        development.append(example_id)
        replacements[example_id] = replacement.example_id
    return selected, {"seed": seed, "development": development, "pilot_check": check,
                      "inspected_during_design": list(inspected), "check_replacements": replacements,
                      "purpose": "RQ1 representation only; not diagnosis calibration"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--holistic", type=Path)
    parser.add_argument("--prompt", help="Exact dataset prompt name; omit to import all")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pilot-size", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inspected", action="append", default=[], metavar="EXAMPLE_ID",
                        help="Essay examined during method design; kept out of pilot_check (repeatable)")
    args = parser.parse_args()
    if args.pilot_size < 0:
        parser.error("--pilot-size must be nonnegative")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Output directory must be empty; choose a new directory to preserve prior runs")
    records, report = load_persuade(args.input, holistic_path=args.holistic, prompt_name=args.prompt)
    pilot, splits = select_pilot(records, args.pilot_size, args.seed, args.inspected) if args.pilot_size else ([], None)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    def write_jsonl(name, items):
        with (args.output_dir / name).open("w") as handle:
            for record in items:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    write_jsonl("records.jsonl", records)
    if splits:
        write_jsonl("pilot.jsonl", pilot)
        (args.output_dir / "splits.json").write_text(json.dumps(splits, indent=2) + "\n")
    (args.output_dir / "import_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("essays", "annotation_rows", "recovery_methods", "unresolved_reasons")}, indent=2))


if __name__ == "__main__":
    main()
