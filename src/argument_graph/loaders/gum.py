"""Import GUM documents as records plus expert eRST gold graphs.

GUM (Georgetown University Multilayer corpus; Zeldes et al. 2025) is annotated in
eRST, the scheme `graph_schema.py` adapts. Its dependency files (`rst/dependencies/*.rsd`)
use the same head-ordered conversion as this project: each EDU points from satellite to
nucleus, multinuclear members chain to the first member, and the root has head 0. So
the gold graph is GUM's own tree with character offsets added, not a reinterpretation.

The text is rebuilt from the sentence strings in `dep/*.conllu` (`# text =`), joined by
a space within a paragraph and a blank line between paragraphs (`# newpar`). EDU tokens
are located in order in that text; a gap between tokens that is not whitespace fails.

The gold graphs keep GUM's full label inventory, including labels this project does not
use, and have no role, stance or polarity (GUM does not annotate them). Signals are not
imported. Secondary edges are kept but not scored. The record prompt says that no
assignment question exists, because the extractor expects one.

    PYTHONPATH=src python3 -m argument_graph.loaders.gum --gum-dir <GUM checkout> \
      --doc GUM_essay_fear --doc GUM_letter_mandela --output-dir data/processed/gum_v1
"""
import argparse
import hashlib
import json
from pathlib import Path

from ..graph_schema import SCHEMA_VERSION
from ..schemas import ExampleRecord

# GUM's standard test partition, essay and letter genres: the closest to argumentative letters.
DEFAULT_DOCS = ["GUM_essay_fear", "GUM_essay_system", "GUM_letter_attorney", "GUM_letter_mandela"]


def read_conllu(path):
    """Return (text, meta) with paragraphs separated by a blank line."""
    paragraphs, meta = [], {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# meta::"):
            key, _, value = line[len("# meta::"):].partition(" = ")
            meta[key] = value
        elif line.startswith("# newpar") and not line.startswith("# newpar_block"):
            paragraphs.append([])
        elif line.startswith("# text = "):
            if not paragraphs:
                paragraphs.append([])
            paragraphs[-1].append(line[len("# text = "):])
    return "\n\n".join(" ".join(p) for p in paragraphs if p), meta


def read_rsd(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        rows.append({"edu": int(cols[0]), "tokens": cols[1].split(" "), "head": int(cols[6]),
                     "label": cols[7], "secondary": cols[8]})
    return rows


def base_label(label):
    """'joint-list_m' -> 'joint-list'."""
    return label.rsplit("_", 1)[0] if label.endswith(("_r", "_m")) else label


def locate_edus(text, rows):
    """Character offsets for each EDU, by finding its tokens in order."""
    pos, spans = 0, []
    for row in rows:
        start = None
        for tok in row["tokens"]:
            found = text.find(tok, pos)
            if found < 0 or text[pos:found].strip():
                raise ValueError(f"EDU {row['edu']}: token {tok!r} not found at {pos} ({text[pos:pos + 40]!r})")
            start = found if start is None else start
            pos = found + len(tok)
        spans.append((start, pos))
    if text[pos:].strip():
        raise ValueError(f"text after the last EDU is not covered: {text[pos:pos + 40]!r}")
    return spans


def convert(gum_dir, doc):
    text, meta = read_conllu(gum_dir / "dep" / f"{doc}.conllu")
    rows = read_rsd(gum_dir / "rst" / "dependencies" / f"{doc}.rsd")
    spans = locate_edus(text, rows)
    units = [{"id": f"u{r['edu']}", "start": s, "end": e, "text": text[s:e]} for r, (s, e) in zip(rows, spans)]
    relations, root = [], None
    for r in rows:
        if r["head"] == 0:
            if root:
                raise ValueError(f"{doc}: more than one root")
            root = f"u{r['edu']}"
            continue
        relations.append({"id": f"r{len(relations) + 1}", "source": f"u{r['edu']}", "target": f"u{r['head']}",
                          "label": base_label(r["label"]), "tier": "primary"})
    for r in rows:
        for edge in filter(None, r["secondary"].split("|") if r["secondary"] != "_" else []):
            target, label = edge.split(":")[:2]
            relations.append({"id": f"r{len(relations) + 1}", "source": f"u{r['edu']}", "target": f"u{target}",
                              "label": base_label(label), "tier": "secondary"})
    example_id = f"gum:{doc}"
    genre, title = meta.get("genre", "text"), meta.get("title", doc)
    record = ExampleRecord(
        example_id=example_id, response_text=text,
        prompt=f"No assignment question is available. The text is a published {genre} from the GUM corpus, titled \"{title}\".",
        metadata={"dataset": "GUM", "document": doc, "genre": genre, "title": title,
                  "source_url": meta.get("sourceURL"), "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
    record.validate()
    gold = {"schema_version": SCHEMA_VERSION, "example_id": example_id, "root": root, "units": units,
            "relations": relations,
            "provenance": {"annotator": "GUM (expert eRST annotation)", "review_status": "expert_annotated",
                           "source": f"https://github.com/amir-zeldes/gum rst/dependencies/{doc}.rsd",
                           "note": "GUM labels kept as annotated; no role, stance, polarity or signals"}}
    return record, gold


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gum-dir", type=Path, required=True, help="Checkout of github.com/amir-zeldes/gum")
    parser.add_argument("--doc", action="append", default=[], help=f"Document name (repeatable); default {DEFAULT_DOCS}")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    docs = args.doc or DEFAULT_DOCS
    gold_dir = args.output_dir / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "records.jsonl").open("w") as handle:
        for doc in docs:
            record, gold = convert(args.gum_dir, doc)
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            (gold_dir / f"{doc}.json").write_text(json.dumps(gold, indent=2, ensure_ascii=False))
            primary = sum(r["tier"] == "primary" for r in gold["relations"])
            print(f"{doc}: {len(record.response_text.split())} words, {len(gold['units'])} EDUs, {primary} primary edges")
    (args.output_dir / "splits.json").write_text(json.dumps({"development": [], "pilot_check": [], "gum": [f"gum:{d}" for d in docs],
                                                             "note": "GUM documents are held out: never used to design prompts"}, indent=2))


if __name__ == "__main__":
    main()
