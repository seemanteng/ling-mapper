"""Model-free baselines that write graphs in the same layout as an extraction run.

They show what a score is worth without a language model, and `evaluate.py` scores them like any run
(`--run-dir` the folder written here). Both use the rule-based splitter in `presegment`, so
their segmentation scores are not independent evidence: the reference segments were started from
the same splitter. Compare models with them on role, stance, root and attachment instead.

- `majority`: the first unit is the root and position, every other unit is endorsed evidence
  attached to the root as `explanation-justify`, the most common support label in the reference set.
- `rules`: cue-based. The root is the first unit with a thesis cue ("I think", "I agree", "should"),
  else the first unit. Units before it are leads attached as `context-background`; units in the last
  paragraph (when there is more than one) are concluding summary; the rest are evidence. A unit that
  continues its sentence (it starts a clause with a connective, or the previous unit ends with a
  comma) attaches to the previous unit, otherwise to the root. The label follows the connective:
  but/however/although give `adversative-contrast`, and for example/for instance give
  `explanation-evidence`, otherwise `explanation-justify` or `elaboration-additional`.

Neither baseline ever produces a counterclaim, rebuttal, conceded or rejected unit, so their
scores on those classes are zero by construction.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from .graph_schema import SCHEMA_VERSION, argument_edges, validate_graph
from .presegment import presegment
from .schemas import ExampleRecord

THESIS_CUES = re.compile(r"\b(i (think|believe|agree|disagree|feel|support|oppose|am for|am against|would)|in my opinion|"
                         r"should|would benefit|would be better|is better|are better|beneficial|i prefer)\b", re.I)
CONCLUSION_CUES = re.compile(r"^\s*(in conclusion|to conclude|in summary|to sum up|overall|finally|all in all)\b", re.I)
CONTRAST = re.compile(r"^\s*(but|however|although|though|yet|while|whereas|on the other hand)\b", re.I)
EXAMPLE = re.compile(r"^\s*(for example|for instance|such as|like)\b", re.I)
CONTINUES = re.compile(r"^\s*(and|or|but|because|so|which|who|that|since|if|when|while|although|though|then|also|cuz)\b", re.I)


def _units(text, spans, root_at):
    paragraphs = [m.start() for m in re.finditer(r"\n\s*\n", text)]
    last_break = paragraphs[-1] if paragraphs else None
    units = []
    for i, (s, e) in enumerate(spans, 1):
        piece = text[s:e]
        if i - 1 == root_at:
            role = "position"
        elif i - 1 < root_at:
            role = "lead"
        elif last_break is not None and s > last_break:
            role = "concluding_summary"
        else:
            role = "evidence"
        units.append({"id": f"u{i}", "start": s, "end": e, "text": piece, "role": role,
                      "stance": "endorsed", "polarity": "positive"})
    return units


def majority_graph(example_id, text):
    spans = presegment(text)
    units = _units(text, spans, 0)
    for u in units[1:]:
        u["role"] = "evidence"
    relations = [{"id": f"r{n}", "source": u["id"], "target": "u1", "label": "explanation-justify", "tier": "primary",
                  "signals": [], "implicit": True} for n, u in enumerate(units[1:], 1)]
    return {"schema_version": SCHEMA_VERSION, "example_id": example_id, "root": "u1", "units": units, "relations": relations}


def rules_graph(example_id, text):
    spans = presegment(text)
    root_at = next((i for i, (s, e) in enumerate(spans) if THESIS_CUES.search(text[s:e])), 0)
    units = _units(text, spans, root_at)
    root = units[root_at]["id"]
    relations = []
    for i, u in enumerate(units):
        if i == root_at:
            continue
        previous = units[i - 1] if i else None
        piece = u["text"]
        continues = previous is not None and i > root_at and (CONTINUES.match(piece) or previous["text"].rstrip().endswith(","))
        target = previous["id"] if continues else root
        if i < root_at:
            label = "context-background"
        elif CONTRAST.match(piece) and target != root:
            label = "adversative-contrast"
        elif EXAMPLE.match(piece):
            label = "explanation-evidence"
        elif continues:
            label = "elaboration-additional"
        else:
            label = "explanation-justify"
        if u["role"] == "concluding_summary" and CONCLUSION_CUES.match(piece):
            label = "restatement-partial"
        if i < root_at:
            target = root
        relations.append({"id": f"r{len(relations) + 1}", "source": u["id"], "target": target, "label": label,
                          "tier": "primary", "signals": [], "implicit": True})
    return {"schema_version": SCHEMA_VERSION, "example_id": example_id, "root": root, "units": units, "relations": relations}


BASELINES = {"majority": majority_graph, "rules": rules_graph}


def write_run(name, records_path, out_dir, essays=None):
    """Write `<id>.graph.json` and a manifest for each essay; returns {essay: validation errors}."""
    with Path(records_path).open() as handle:
        records = [ExampleRecord.from_dict(r) for r in map(json.loads, handle)]
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"prompt_version": f"baseline/{name}", "config_hash": hashlib.sha256(name.encode()).hexdigest()[:16],
                "provider": "none", "model": f"baseline-{name}", "effort": "none", "schema_version": SCHEMA_VERSION,
                "records": str(records_path), "essays": {}}
    problems = {}
    for record in records:
        if essays and record.example_id not in essays:
            continue
        text = record.response_text
        graph = BASELINES[name](record.example_id, text)
        errors = validate_graph(graph, text)
        if errors:
            problems[record.example_id] = errors
            manifest["essays"][record.example_id] = {"status": "failed_validation", "attempts": 0, "input_tokens": 0, "output_tokens": 0}
            continue
        graph["provenance"] = {"annotator": f"baseline-{name}", "review_status": "not_human_reviewed",
                               "config_hash": manifest["config_hash"]}
        (out_dir / f"{record.example_id.split(':', 1)[-1]}.graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False))
        manifest["essays"][record.example_id] = {"status": "ok", "attempts": 0, "input_tokens": 0, "output_tokens": 0,
                                                 "units": len(graph["units"]), "relations": len(graph["relations"]),
                                                 "derived": len(argument_edges(graph))}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="Parent folder; one subfolder per baseline")
    parser.add_argument("--baseline", action="append", choices=sorted(BASELINES), help="Default: all")
    args = parser.parse_args()
    for name in args.baseline or sorted(BASELINES):
        problems = write_run(name, args.records, args.output_dir / f"baseline-{name}")
        print(f"{name}: {len(problems)} essays failed validation")
        for essay, errors in problems.items():
            print("  ", essay, errors[:2])


if __name__ == "__main__":
    main()
