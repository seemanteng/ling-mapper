"""Align student graph units with source graph units (Phase C prototype).

For each unit of a student graph, a model judge decides which source units it draws on and how
faithfully: `quote` (copies the source's wording), `paraphrase` (same proposition, faithful),
`distorted` (based on the source but changed: reversed, wrong number, name or date, misused
example, overgeneralised), `related` (uses source content to assert something the source does
not), or `none` (no source basis: opinion, rhetoric, personal or outside knowledge).

The three sources are short, so the judge sees every source unit (with source, paragraph, type
and the author's stance) rather than retrieved candidates. It sees the student's essay and unit
texts only: no roles, stances or relations, so gold graphs can be used as input without leaking
annotations. Word overlap gives a free baseline. Outputs are validated like extraction output:
failed checks are sent back for a bounded number of attempts and never repaired silently.
"""
import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from .student_graph import DEFAULT_MODEL, _run_stage

LABELS = ["quote", "paraphrase", "distorted", "related", "none"]
LINKED = {"quote", "paraphrase", "distorted"}
PROMPT_VERSION = "align/0.2"

SYSTEM = """You compare a student's essay with the reading passages it was written from, for research on how students use sources. You judge fidelity to the passages, not whether claims are true.

For every student unit you are given, decide whether it draws on the passages and how:
- quote: copies the passage's wording (spelling slips and small changes allowed).
- paraphrase: states the same proposition as the passage unit(s) in other words, without changing its meaning.
- distorted: is based on specific passage unit(s) but changes the meaning: reverses a claim, gets a number, name, date or example wrong, applies an example to a point it does not show, overstates a claim (possible becomes bound to happen, more becomes the only ones, most votes becomes a majority), asserts something a passage unit contradicts (unless another passage supports it: siding with one source is not distorting the other), or states as the author's view something the author only reports or concedes.
- related: uses specific passage content (a particular fact, number, example or named argument) to assert something the passages do not say, such as the student's own inference or combination.
- none: has no basis in the passages: the student's opinion, rhetoric, or personal or outside knowledge. A stance, evaluation or call to action that only agrees with a passage's position ("we should abolish the Electoral College", "the system is unfair") is none, even if a passage says the same in general terms.

Rules:
- For quote, paraphrase and distorted, list every passage unit the student unit draws on (a student often compresses several), and no more: do not add neighbouring units the student does not use. For related, list the units whose content is used, if any. For none, list none.
- Attend to the author's stance: a passage unit marked as an opposing view or a concession is not the author's own position.
- A student's citation ("paragraph 12", "Source 2") is evidence about which unit is meant, but check the content: citations can be wrong.
- For distorted, say in the note exactly what changed. Otherwise keep the note short or empty.
- Judge each unit in the context of the essay (pronouns, ellipsis), but align only what the unit itself asserts.
- Label a unit by what it asserts, even when it repeats a point the student made earlier (an introduction's preview or a conclusion's summary of a source-based point is aligned like the point itself)."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["alignments"],
    "properties": {"alignments": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["unit", "label", "source_units", "note"],
        "properties": {"unit": {"type": "string"}, "label": {"type": "string", "enum": LABELS},
                       "source_units": {"type": "array", "items": {"type": "string"}}, "note": {"type": "string"}}}}},
}


def load_sources(source_dir):
    """Return {source unit id: info} and the prompt listing, from the gitignored source graphs."""
    source_dir = Path(source_dir)
    records = {json.loads(l)["example_id"]: json.loads(l) for l in open(source_dir / "source_records.jsonl")}
    units, blocks = {}, []
    for path in sorted((source_dir / "reference").glob("S*.source_graph.json")):
        g = json.loads(path.read_text())
        meta = records[g["example_id"]]["metadata"]
        sid = meta["source_id"]
        blocks.append(f'<source id="{sid}" title="{meta["title"]}" author="{meta["author"]}">')
        for u in g["units"]:
            units[u["id"]] = dict(u, source=sid)
            stance = {"conceded": " (conceded by the author)", "reported": " (opposing view, reported by the author)"}.get(u["stance"], "")
            blocks.append(f'{u["id"]} [{sid} ¶{u["paragraph"] or "-"} {u["type"]}{stance}] {u["text"]}')
        blocks.append("</source>")
    return units, "\n".join(blocks)


def check(data, unit_ids, source_units):
    """Validate a judge answer; return (alignments by unit, errors)."""
    errors, out = [], {}
    for a in data.get("alignments", []):
        uid = a.get("unit")
        if uid not in unit_ids:
            errors.append(f"unknown student unit {uid!r}")
        elif uid in out:
            errors.append(f"student unit {uid} is aligned twice")
        unknown = [s for s in a.get("source_units", []) if s not in source_units]
        if unknown:
            errors.append(f"{uid}: unknown source units {unknown}")
        if a.get("label") in LINKED and not a.get("source_units"):
            errors.append(f"{uid}: label {a.get('label')} needs at least one source unit")
        if a.get("label") == "none" and a.get("source_units"):
            errors.append(f"{uid}: label none must not list source units")
        if a.get("label") == "distorted" and not a.get("note", "").strip():
            errors.append(f"{uid}: distorted needs a note saying what changed")
        out[uid] = {"label": a.get("label"), "source_units": a.get("source_units", []), "note": a.get("note", "")}
    missing = [u for u in unit_ids if u not in out]
    if missing:
        errors.append(f"no alignment for student units {missing}")
    return out, errors


def judge(record, graph, caller, source_units, listing, max_attempts=3, attempts=None):
    unit_ids = [u["id"] for u in graph["units"]]
    listed = set(source_units)
    units = "\n".join(f'{u["id"]}: {u["text"]}' for u in graph["units"])
    content = (f"<passages>\n{listing}\n</passages>\n\n<assignment>\n{record['prompt']}\n</assignment>\n\n"
               f"<essay>\n{record['response_text']}\n</essay>\n\n<student_units>\n{units}\n</student_units>\n\n"
               "Align every student unit.")
    attempts = [] if attempts is None else attempts
    result = _run_stage(caller, SYSTEM, [{"role": "user", "content": content}], SCHEMA,
                        lambda d: check(d, unit_ids, listed), max_attempts, "align", attempts)
    return {"alignments": result, "attempts": attempts}


def _tokens(text):
    stop = set("the a an of to in and or is are was were be been it its that this for on by as at with from their they "
               "his her he she you your we our not but have has had will would can could do does did than which who what "
               "there so if all no".split())
    return [w for w in re.findall(r"[a-z0-9]+", text.lower().replace(",", "")) if w not in stop and len(w) > 2]


def baseline(graph, source_units, strong=0.6, weak=0.3):
    """Word-overlap baseline: the best-matching source unit by idf-weighted cosine over word sets."""
    pool = source_units
    df = Counter(w for v in pool.values() for w in set(_tokens(v["text"])))
    idf = {w: math.log((len(pool) + 1) / (c + 1)) for w, c in df.items()}
    def score(a, b):
        A, B = set(_tokens(a)), set(_tokens(b))
        wa, wb = sum(idf.get(w, math.log(len(pool) + 1)) for w in A), sum(idf.get(w, math.log(len(pool) + 1)) for w in B)
        return sum(idf.get(w, 0) for w in A & B) / math.sqrt(wa * wb) if wa and wb else 0.0
    out = {}
    for u in graph["units"]:
        best, s = max(((k, score(u["text"], v["text"])) for k, v in pool.items()), key=lambda x: x[1])
        label = "quote" if s >= strong else "related" if s >= weak else "none"
        out[u["id"]] = {"label": label, "source_units": [best] if label != "none" else [], "note": f"overlap {s:.2f}"}
    return out


def score(pred, gold, source_units):
    """Compare alignments for the units in `gold`. Returns label, detection, link and distortion scores."""
    n = agree = 0
    tp_det = fp_det = fn_det = 0
    tp_link = n_pred_link = n_gold_link = 0
    src_agree = src_n = 0
    dist = Counter()
    confusion = Counter()
    for uid, g in gold.items():
        p = pred.get(uid, {"label": "none", "source_units": []})
        n += 1
        agree += p["label"] == g["label"]
        confusion[(g["label"], p["label"])] += 1
        used_g, used_p = g["label"] != "none", p["label"] != "none"
        tp_det += used_g and used_p; fp_det += used_p and not used_g; fn_det += used_g and not used_p
        gl = set(g["source_units"]) if g["label"] in LINKED else set()
        pl = set(p["source_units"]) if p["label"] in LINKED else set()
        tp_link += len(gl & pl); n_pred_link += len(pl); n_gold_link += len(gl)
        if gl and pl:
            src_n += 1
            src_agree += {source_units[x]["source"] for x in gl} == {source_units[x]["source"] for x in pl if x in source_units}
        dist[(g["label"] == "distorted", p["label"] == "distorted")] += 1
    f1 = lambda tp, fp, fn: round(2 * tp / (2 * tp + fp + fn), 4) if tp else 0.0
    return {"units": n, "label_accuracy": round(agree / n, 4) if n else 0.0,
            "source_use_f1": f1(tp_det, fp_det, fn_det),
            "link_precision": round(tp_link / n_pred_link, 4) if n_pred_link else 0.0,
            "link_recall": round(tp_link / n_gold_link, 4) if n_gold_link else 0.0,
            "link_f1": f1(tp_link, n_pred_link - tp_link, n_gold_link - tp_link),
            "same_source_when_both_link": round(src_agree / src_n, 4) if src_n else None,
            "distortion": {"gold": dist[(True, True)] + dist[(True, False)], "found": dist[(True, True)],
                           "false_alarms": dist[(False, True)]},
            "confusion": [{"gold": g, "predicted": p, "count": c} for (g, p), c in confusion.most_common()]}


def config_hash(model, effort, listing):
    blob = json.dumps([PROMPT_VERSION, SYSTEM, SCHEMA, model, effort, hashlib.sha256(listing.encode()).hexdigest()], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="Align student graphs with the model judge")
    run.add_argument("--graph", type=Path, action="append", required=True, help="Student graph JSON (repeatable)")
    run.add_argument("--records", type=Path, required=True)
    run.add_argument("--sources", type=Path, default=Path("data/sources/electoral_college"))
    run.add_argument("--output-dir", type=Path, default=Path("data/runs/align"))
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    run.add_argument("--force", action="store_true")
    sc = sub.add_parser("score", help="Score a run and the word-overlap baseline against gold alignments")
    sc.add_argument("--run-dir", type=Path, help="Judge run folder (omit to score only the baseline)")
    sc.add_argument("--gold-dir", type=Path, default=Path("data/annotations/alignments"))
    sc.add_argument("--sources", type=Path, default=Path("data/sources/electoral_college"))
    args = parser.parse_args()
    source_units, listing = load_sources(args.sources)
    if args.cmd == "run":
        from .student_graph import AnthropicCaller
        records = {json.loads(l)["example_id"]: json.loads(l) for l in open(args.records)}
        key = config_hash(args.model, args.effort, listing)
        run_dir = args.output_dir / f"{PROMPT_VERSION.replace('/', '-')}_{args.model}_{args.effort}_{key}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "system_prompt.txt").write_text(SYSTEM)
        caller = AnthropicCaller(args.model, args.effort)
        for path in args.graph:
            graph = json.loads(path.read_text())
            name = graph["example_id"].split(":")[-1]
            out = run_dir / f"{name}.align.json"
            if out.exists() and not args.force:
                print(f"{name}: cached"); continue
            attempts = []
            try:
                result = judge(records[graph["example_id"]], graph, caller, source_units, listing, attempts=attempts)
            except Exception as exc:  # keep the log of one failed essay and continue the batch
                result = {"alignments": None, "attempts": attempts + [{"stage": "error", "error": f"{type(exc).__name__}: {exc}"}]}
            usage = [a.get("usage", {}) for a in result["attempts"]]
            tokens = {"input": sum(u.get("input_tokens", 0) for u in usage), "output": sum(u.get("output_tokens", 0) for u in usage)}
            (run_dir / f"{name}.log.json").write_text(json.dumps(result["attempts"], indent=2, ensure_ascii=False, default=str))
            if result["alignments"] is not None:
                out.write_text(json.dumps({"example_id": graph["example_id"], "student_graph": str(path),
                                           "config_hash": key, "alignments": result["alignments"]}, indent=2, ensure_ascii=False))
            last = result["attempts"][-1] if result["attempts"] else {}
            why = "" if result["alignments"] is not None else f" — {last.get('error') or '; '.join(last.get('errors', []))[:200]}"
            print(f"{name}: {'ok' if result['alignments'] is not None else 'failed'} "
                  f"({len(result['attempts'])} calls, {tokens['input']} in / {tokens['output']} out tokens){why}")
    else:
        golds = {json.loads(p.read_text())["example_id"]: json.loads(p.read_text()) for p in sorted(args.gold_dir.glob("*.json"))}
        systems = {"baseline": {}}
        for eid, gold in golds.items():
            graph = json.loads(Path(gold["student_graph"]).read_text())
            systems["baseline"].update({(eid, k): v for k, v in baseline(graph, source_units).items()})
            if args.run_dir:
                p = args.run_dir / f"{eid.split(':')[-1]}.align.json"
                if p.exists():
                    systems.setdefault("judge", {}).update({(eid, k): v for k, v in json.loads(p.read_text())["alignments"].items()})
        gold_all = {(eid, k): v for eid, g in golds.items() for k, v in g["alignments"].items()}
        report = {}
        for name, pred in systems.items():  # score each system only on the essays it covers
            essays = {e for e, _ in pred}
            report[name] = dict(score(pred, {k: v for k, v in gold_all.items() if k[0] in essays}, source_units),
                                essays=len(essays))
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
