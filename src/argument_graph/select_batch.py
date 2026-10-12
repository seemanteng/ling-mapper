"""CLI that draws a score-band-balanced batch of new essays for self-annotation.

Tops up an existing record set so every holistic score band reaches the same
count, skipping essays already in it. Annotation sheets are written by
`presegment`.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .loaders.persuade import load_persuade
from .schemas import ExampleRecord

def seeded_key(seed, example_id):
    return hashlib.sha256(f"{seed}:{example_id}".encode()).hexdigest()


def band_quotas(existing, target_per_band, bands):
    counts = Counter(r.metadata.get("holistic_score") for r in existing)
    over = {band: counts[band] for band in bands if counts[band] > target_per_band}
    if over:
        raise ValueError(f"Existing essays already exceed the target in bands {over}")
    return {band: target_per_band - counts[band] for band in bands}


def select_batch(pool, existing, target_per_band, seed):
    """Return new records ordered by band then seeded position, plus the quotas."""
    taken = {r.example_id for r in existing}
    groups = defaultdict(list)
    for record in pool:
        if record.example_id not in taken:
            groups[record.metadata.get("holistic_score")].append(record)
    bands = sorted({b for b in groups} | {r.metadata.get("holistic_score") for r in existing}, key=str)
    bands = [b for b in bands if b]
    quotas = band_quotas(existing, target_per_band, bands)
    selected = []
    for band in bands:
        candidates = sorted(groups[band], key=lambda r: seeded_key(seed, r.example_id))
        if len(candidates) < quotas[band]:
            raise ValueError(f"Band {band} needs {quotas[band]} essays; only {len(candidates)} available")
        selected.extend(candidates[:quotas[band]])
    return selected, quotas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True,
                        help="PERSUADE CSV to draw from (repeatable)")
    parser.add_argument("--holistic", type=Path)
    parser.add_argument("--prompt", required=True, help="Exact dataset prompt name")
    parser.add_argument("--existing", type=Path, required=True, help="Directory holding records.jsonl and splits.json")
    parser.add_argument("--target-per-band", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split-name", default="self_annotation_batch3")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Output directory must be empty; choose a new directory to preserve prior runs")
    existing_lines = (args.existing / "records.jsonl").read_text(encoding="utf-8").splitlines()
    existing = [ExampleRecord.from_dict(json.loads(line)) for line in existing_lines if line.strip()]
    pool = []
    for path in args.input:
        records, _ = load_persuade(path, holistic_path=args.holistic, prompt_name=args.prompt)
        pool.extend(records)
    selected, quotas = select_batch(pool, existing, args.target_per_band, args.seed)
    splits = json.loads((args.existing / "splits.json").read_text())
    splits[args.split_name] = [r.example_id for r in selected]
    splits[f"{args.split_name}_selection"] = {
        "seed": args.seed, "prompt": args.prompt, "target_per_band": args.target_per_band,
        "quotas": quotas, "excluded_existing": [r.example_id for r in existing],
        "inputs": [str(p) for p in args.input],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "records.jsonl").open("w", encoding="utf-8") as handle:
        for line in existing_lines:
            if line.strip():
                handle.write(line + "\n")
        for record in selected:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    (args.output_dir / "splits.json").write_text(json.dumps(splits, indent=2) + "\n")
    print(json.dumps({"quotas": quotas, "selected": [
        (r.example_id, r.metadata.get("holistic_score"), r.metadata.get("official_split")) for r in selected]}, indent=1))


if __name__ == "__main__":
    main()
