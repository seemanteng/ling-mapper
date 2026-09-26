"""Fetch the reading passages for the PERSUADE prompt 'Does the electoral college work?'.

The PERSUADE records carry only source titles. The passages, with the paragraph numbers
students cite ("paragraph 12"), were released by the same organisers in the Kaggle
competition "LLM - Detect AI Generated Text" (train_prompts.csv). That file needs a Kaggle
login, so this script downloads a public copy pinned to a commit and checks its SHA-256.
The copy is GBK-encoded (curly quotes read as '¡¯' in cp1252); it is decoded as GBK, so the
text is not otherwise altered. Compare with Kaggle's original when you can.

Two of the three passages (Plumer, Mother Jones 2004; Posner, Slate 2012) are copyrighted
excerpts, so the output directory is gitignored: commit this script, not the text.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
from pathlib import Path

URL = ("https://raw.githubusercontent.com/Lizhecheng02/Kaggle-LLM-Detect_AI_Generated_Text/"
       "d5c56d6efa755b022d2d082dcd91a4bab0eb59c2/new_train_prompts.csv")
CSV_SHA256 = "b234ffadb17090b2faf648dc109eae25c523c8d6bf57e10fa215743b09e9cfc0"
TEXT_SHA256 = "636d99a95378700a44aa42e521c631cd99aeeea0072f180cbabfcf20ca8271a9"
PROMPT_NAME = "Does the electoral college work?"


def parse(raw):
    """Return (instructions, source_text) for the electoral-college prompt from the CSV bytes."""
    csv.field_size_limit(10_000_000)
    rows = csv.DictReader(io.StringIO(raw.decode("gbk")))
    row = next(r for r in rows if r["prompt_name"] == PROMPT_NAME)
    return row["instructions"], row["source_text"]


def paragraphs(text):
    """Map each numbered paragraph to (source title, paragraph text)."""
    out, title = {}, None
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        m = re.match(r"(\d+) (.*)", line)
        if m:
            out[int(m.group(1))] = {"source": title, "text": m.group(2)}
    return out


SOURCE_IDS = {"What Is the Electoral College?": "S1", "The Indefensible Electoral College": "S2",
              "In Defense of the Electoral College": "S3"}


def documents(text, instructions):
    """One common record per source: its paragraphs without their numbers, joined by blank lines,
    with sub-headings kept as lines. Paragraph numbers go to metadata as offsets."""
    records, current = [], None
    for line in text.splitlines():
        if line.startswith("# "):
            title, _, author = line[2:].partition(" by ")
            sid = next(v for k, v in SOURCE_IDS.items() if title.startswith(k))
            current = {"example_id": f"source:{sid}", "prompt": instructions, "parts": [], "paragraphs": {},
                       "metadata": {"source_id": sid, "title": title.strip(), "author": author.strip()}}
            records.append(current)
            continue
        if not line.strip() or current is None:
            continue
        m = re.match(r"(\d+) (.*)", line)
        body = m.group(2) if m else line.lstrip("# ").strip()
        start = sum(len(x) + 2 for x in current["parts"])
        current["parts"].append(body)
        if m:
            current["paragraphs"][int(m.group(1))] = [start, start + len(body)]
    out = []
    for r in records:
        meta = dict(r["metadata"], paragraphs=r["paragraphs"], document_type="source_passage")
        out.append({"example_id": r["example_id"], "prompt": r["prompt"], "response_text": "\n\n".join(r["parts"]),
                    "source_passages": None, "rubric": None, "gold_spans": None, "gold_relations": None,
                    "metadata": meta, "schema_version": "1.0"})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/sources/electoral_college"))
    parser.add_argument("--csv", type=Path, help="Use an already-downloaded copy (e.g. `curl -LO <URL>`) instead of fetching")
    args = parser.parse_args()
    raw = args.csv.read_bytes() if args.csv else urllib.request.urlopen(URL, timeout=60).read()
    got = hashlib.sha256(raw).hexdigest()
    if got != CSV_SHA256:
        raise SystemExit(f"Downloaded file changed (sha256 {got}); inspect it before updating CSV_SHA256.")
    instructions, text = parse(raw)
    if hashlib.sha256(text.encode()).hexdigest() != TEXT_SHA256:
        raise SystemExit("Decoded passage text differs from the verified version.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "source_text.md").write_text(text)
    (args.output_dir / "instructions.txt").write_text(instructions)
    (args.output_dir / "paragraphs.json").write_text(json.dumps(paragraphs(text), indent=2, ensure_ascii=False))
    with (args.output_dir / "source_records.jsonl").open("w") as handle:
        for rec in documents(text, instructions):
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    (args.output_dir / "provenance.json").write_text(json.dumps({
        "prompt_name": PROMPT_NAME, "url": URL, "csv_sha256": CSV_SHA256, "text_sha256": TEXT_SHA256,
        "encoding": "gbk", "origin": "Kaggle 'LLM - Detect AI Generated Text' train_prompts.csv (The Learning Agency Lab), via a public GitHub copy",
        "status": "second-hand copy; paragraph numbers match student citations; not yet compared with Kaggle's original file"}, indent=2))
    print(json.dumps({"paragraphs": len(paragraphs(text)), "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
