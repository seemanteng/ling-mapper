"""Extract an argument_graph/0.1 from one essay with Claude, in two validated stages.

Stage 1 (segment): the model returns units as exact quotes; code locates them in the
unchanged essay and checks that they tile it. Stage 2 (relate): the model returns
roles, stances, the primary tree, secondary edges and signal quotes; code locates the
signals and runs `validate_graph`. On failure the exact errors are sent back for a
bounded number of attempts. Nothing is repaired silently, and a graph that never
validates is saved as a failure, not as an empty graph.

The model sees only `ExampleRecord.model_input()` (assignment prompt and essay text):
no gold annotations, scores or dataset metadata. The contract text is generated from
`graph_schema.py` so the prompt and the validator cannot drift apart.
"""
import argparse
import hashlib
import json
import time
import traceback
from pathlib import Path

from .graph_schema import RELATIONS, ROLES, SCHEMA_VERSION, SIGNAL_TYPES, STANCES, argument_edges, validate_graph
from .schemas import ExampleRecord

PROMPT_VERSION = "student_graph/0.2"
DEFAULT_MODEL = "claude-opus-5"

ROLE_DEFINITIONS = {
    "lead": "everything in the introduction before the position, including the writer's general opinions and questions",
    "position": "the writer's answer to the assignment question (the thesis)",
    "claim": "the statement of one reason for the position, usually one sentence opening a body paragraph",
    "counterclaim": "the statement of an opposing view, usually one sentence",
    "rebuttal": "the statement of the writer's answer to a counterclaim",
    "evidence": "everything that develops a claim, counterclaim or rebuttal: examples, facts, quotes, explanation, consequences and the writer's commentary",
    "concluding_summary": "closing restatement of the position and claims",
    "unannotated": "text that plays none of these roles (greetings, sign-offs, asides)",
}
STANCE_DEFINITIONS = {
    "endorsed": "the writer puts this forward as their own view",
    "conceded": "the writer grants it (typically before arguing past it)",
    "rejected": "the writer presents it as an alternative they reject",
    "reported": "attributed to others or presented without the writer taking it on",
    "unclear": "none of the above can be decided from the text",
}
SEGMENTATION_RULES = """\
1. Every sentence is at least one unit; a unit never crosses a paragraph break.
2. Split clauses that each have their own predicate when joined by a conjunction or discourse marker (and, but, because, although, if, so, while), including non-finite clauses introduced by a marker (instead of ...-ing, by ...-ing). Predicates that share one subject are split too: "won votes | and lost the presidency"; "it limits representation, | permits the disintrest of voters, | and reduces a candidates intrest". Coordinated noun phrases, adjectives and objects stay together ("good and bad things").
3. Do not split restrictive relative clauses or the complement of a non-reporting verb.
4. Split a reporting frame from its content only when the source is not the writer ("Posner argues | that ..."); link them with attribution-positive. The writer's own "I think/I believe" stays inside the unit.
5. Headings and list labels ("Certainty of outcome:") are their own unit.
6. Citations such as "(Posner, paragraph 22)" stay inside the unit they cite.
7. An aside with its own predicate that interrupts a unit ("induces candidates-as we saw in 2012's election-to focus ...") is its own unit; the interrupted parts are separate units later joined by same-unit. Parenthetical noun phrases stay inside."""
ROLE_RULES = """\
- Roles follow the essay's element structure, not the stance of each unit. A conceded, reported or rejected unit can be evidence, and an opinion can be evidence.
- A body paragraph normally holds one claim (or one counterclaim or rebuttal) and evidence. The claim is the unit or sentence stating the reason; the sentences after it that develop that reason are evidence, even when they are the writer's opinions, evaluations ("that is just evil"), consequences or restatements of the reason.
- A counterclaim is the statement of the opposing view. The quotes, details and explanation that develop the opposing view are evidence. A concessive clause ("Although ...", "However it could ...") inside a paragraph developing the writer's own claim is evidence, not a counterclaim.
- The position is the unit that answers the assignment question (for example: keep the Electoral College, or change to the popular vote), and the root is its main clause. General opinions or questions about the topic that come before it are lead, not claims and not the position, even when they sound argumentative."""
STRUCTURE_RULES = """\
- Every relation points from satellite (source, the less central unit) to nucleus (target). Multinuclear relations (marked below) chain each later member to the first member.
- Primary tree: exactly one root (the central unit, normally the main clause of the thesis); every other unit has exactly one primary relation to its head; no cycles. Build the whole primary tree first.
- Secondary relations add a further, tree-breaking relation and are allowed only when a quoted signal in the essay licenses it; never duplicate a primary relation. same-unit is primary only and joins parts separated by the interrupting unit; relations of the whole attach to its first part.
- Give each relation the words that signal it (quoted exactly from the source or target unit) with a signal type, or no signals if it is implicit.
- Stance must agree with structure: the satellite of adversative-concession is conceded; the satellite of adversative-antithesis is rejected; every conceded or rejected unit takes part in an adversative relation.
- Label tests: evidence when S is a fact, example, statistic or source that makes N more believable, justify when S is the writer's reason for holding or saying N; concession when the writer grants S, antithesis when S is an alternative the writer rejects; cause/result only for causation stated as content; mode-means when S says how N is achieved; topic-solutionhood when S states a problem and N the fix; topic-question when S is a question that N answers; elaboration-additional only when nothing else applies.
- because, since and so do not decide the label. If N is the writer's judgement, opinion or recommendation ("it is fair", "the process is mature", "we should keep it", "it doesn't prove anything"), S is the writer's reason for it: explanation-justify, or explanation-evidence when S is a fact that makes N more believable. Use causal-cause or causal-result only when N is an event or state in the world that S brings about ("because the state is large, it gets more electors").
- Parallel items at the same level (several facts describing how the system works, a series of reasons or examples) form a joint-list: chain each later item to the first, and attach the list to its head through the first item. Use elaboration-additional only when S adds detail to one particular N, not when S is the next item in a series.
- Represent what the essay says, including factual errors and weak reasoning. Do not correct, improve or judge the student's claims."""


def system_prompt():
    labels = "\n".join(f"- {name}{' (multinuclear)' if kind == 'multinuclear' else ''}: {definition}"
                       for name, (kind, definition) in RELATIONS.items())
    roles = "\n".join(f"- {r}: {ROLE_DEFINITIONS[r]}" for r in sorted(ROLES))
    stances = "\n".join(f"- {s}: {d}" for s, d in STANCE_DEFINITIONS.items())
    return f"""You analyse the argument structure of student essays for research on how students reason. You build a discourse graph following Enhanced Rhetorical Structure Theory (eRST): nodes are clause-level units of the essay, edges are directed rhetorical relations. The graph must be faithful to the essay; a separate stage, not you, judges whether claims are true.

Units tile the essay: every piece of non-whitespace text belongs to exactly one unit, quoted exactly as written (keep the student's spelling, punctuation and spacing).

Segmentation rules:
{SEGMENTATION_RULES}

Relation labels (S = satellite/source, N = nucleus/target, R = reader, W = writer):
{labels}

Structure rules:
{STRUCTURE_RULES}

Unit roles (the essay element a unit belongs to):
{roles}

Role rules:
{ROLE_RULES}

Stances (does the writer put the unit forward as their own view?):
{stances}

Signal types: {", ".join(sorted(SIGNAL_TYPES))}. Use dm for discourse markers such as because, but, however, for example."""


SEGMENT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["units"],
    "properties": {"units": {"type": "array", "items": {"type": "string"}}},
}
RELATE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["root", "units", "relations"],
    "properties": {
        "root": {"type": "string"},
        "units": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "role", "stance", "polarity"],
            "properties": {"id": {"type": "string"}, "role": {"type": "string", "enum": sorted(ROLES)},
                           "stance": {"type": "string", "enum": sorted(STANCES)},
                           "polarity": {"type": "string", "enum": ["positive", "negative"]}}}},
        "relations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["source", "target", "label", "tier", "signals"],
            "properties": {"source": {"type": "string"}, "target": {"type": "string"},
                           "label": {"type": "string", "enum": sorted(RELATIONS)},
                           "tier": {"type": "string", "enum": ["primary", "secondary"]},
                           "signals": {"type": "array", "items": {
                               "type": "object", "additionalProperties": False, "required": ["type", "text"],
                               "properties": {"type": {"type": "string", "enum": sorted(SIGNAL_TYPES)},
                                              "text": {"type": "string"}}}}}}},
    },
}


def config_hash(model, effort):
    blob = json.dumps([PROMPT_VERSION, system_prompt(), SEGMENT_SCHEMA, RELATE_SCHEMA, model, effort], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def locate_units(text, quotes):
    """Map quotes to offsets in order; report missing quotes and uncovered text."""
    units, errors, pos = [], [], 0
    for i, quote in enumerate(quotes, 1):
        if not quote.strip():
            errors.append(f"unit {i} is empty")
            continue
        start = text.find(quote, pos)
        if start == -1:
            where = "anywhere in the essay" if text.find(quote) == -1 else "after the previous unit"
            errors.append(f"unit {i} {quote[:60]!r} is not an exact quote {where}")
            continue
        gap = text[pos:start]
        if gap.strip():
            errors.append(f"text before unit {i} is not covered by any unit: {gap.strip()[:80]!r}")
        units.append({"id": f"u{len(units) + 1}", "start": start, "end": start + len(quote), "text": quote})
        pos = start + len(quote)
    if text[pos:].strip():
        errors.append(f"text after the last unit is not covered: {text[pos:].strip()[:80]!r}")
    return units, errors


def assemble_graph(example_id, text, units, relate):
    """Combine located units with the stage-2 answer; locate signal quotes in the linked units."""
    errors = []
    by_id = {u["id"]: dict(u) for u in units}
    for attrs in relate.get("units", []):
        if attrs.get("id") not in by_id:
            errors.append(f"unit attributes given for unknown id {attrs.get('id')!r}")
            continue
        by_id[attrs["id"]].update(role=attrs["role"], stance=attrs["stance"], polarity=attrs["polarity"])
    missing = [uid for uid, u in by_id.items() if "role" not in u]
    if missing:
        errors.append(f"no role/stance/polarity given for units {missing}")
    relations = []
    for i, r in enumerate(relate.get("relations", []), 1):
        rel = {"id": f"r{i}", "source": r["source"], "target": r["target"], "label": r["label"], "tier": r["tier"], "signals": []}
        for sig in r.get("signals", []):
            found = None
            for uid in (r["source"], r["target"]):
                u = by_id.get(uid)
                if u:
                    a = text.find(sig["text"], u["start"], u["end"]) if sig["text"] else -1
                    if a != -1:
                        found = {"type": sig["type"], "start": a, "end": a + len(sig["text"]), "text": sig["text"]}
                        break
            if found:
                rel["signals"].append(found)
            else:
                errors.append(f"relation {r['source']}->{r['target']}: signal {sig['text']!r} is not an exact quote inside either unit")
        if not rel["signals"]:
            rel["implicit"] = True
        relations.append(rel)
    graph = {"schema_version": SCHEMA_VERSION, "example_id": example_id, "root": relate.get("root"),
             "units": list(by_id.values()), "relations": relations}
    return graph, errors + validate_graph(graph, text)


class AnthropicCaller:
    """One structured-output request per call; returns (data, content_for_history, log)."""

    def __init__(self, model=DEFAULT_MODEL, effort="high"):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model, self.effort = model, effort

    def __call__(self, system, messages, schema):
        started = time.time()
        with self.client.beta.messages.stream(
            model=self.model, max_tokens=64000, system=system, messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        ) as stream:
            response = stream.get_final_message()
        log = {"request_id": getattr(response, "_request_id", None), "model": response.model,
               "stop_reason": response.stop_reason, "usage": response.usage.to_dict(),
               "seconds": round(time.time() - started, 1), "response": response.to_dict()}
        if response.stop_reason != "end_turn":
            return None, response.content, log
        text = next((b.text for b in response.content if b.type == "text"), None)
        try:
            return (json.loads(text) if text else None), response.content, log
        except json.JSONDecodeError as exc:
            log["stop_reason"] = f"invalid_json: {exc}"
            return None, response.content, log


def _run_stage(caller, system, messages, schema, check, max_attempts, stage, attempts):
    for attempt in range(1, max_attempts + 1):
        data, content, log = caller(system, messages, schema)
        if data is None:
            attempts.append({"stage": stage, "attempt": attempt, "errors": [f"no usable output (stop_reason={log.get('stop_reason')})"], **log})
            return None
        result, errors = check(data)
        attempts.append({"stage": stage, "attempt": attempt, "output": data, "errors": errors, **log})
        if not errors:
            return result
        messages = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": "Your output failed these checks:\n" + "\n".join(f"- {e}" for e in errors)
             + "\nReturn a corrected, complete output."}]
    return None


def extract(record, caller, max_attempts=3, attempts=None):
    """Run both stages for one ExampleRecord. Returns {"graph": graph or None, "attempts": [...]}.

    Pass `attempts` to keep the attempts made so far if a call raises.
    """
    inp = record.model_input()
    text, system = inp["response_text"], system_prompt()
    essay = f"<assignment>\n{inp['prompt']}\n</assignment>\n\n<essay>\n{text}\n</essay>"
    attempts = [] if attempts is None else attempts
    units = _run_stage(caller, system, [{"role": "user", "content": essay + "\n\nSegment the essay into units following the segmentation rules. Return every unit as an exact quote, in essay order, so that together they cover all of its non-whitespace text."}],
                       SEGMENT_SCHEMA, lambda d: locate_units(text, d["units"]), max_attempts, "segment", attempts)
    if units is None:
        return {"graph": None, "failed_stage": "segment", "attempts": attempts}
    listing = "\n".join(f"{u['id']}: {u['text']}" for u in units)
    graph = _run_stage(caller, system, [{"role": "user", "content": essay + f"\n\nThe essay is segmented into these units:\n<units>\n{listing}\n</units>\n\nBuild the graph: give every unit its role, stance and polarity, choose the root, add the primary tree and any signalled secondary relations, and quote each relation's signals."}],
                       RELATE_SCHEMA, lambda d: assemble_graph(record.example_id, text, units, d), max_attempts, "relate", attempts)
    if graph is None:
        return {"graph": None, "failed_stage": "relate", "attempts": attempts}
    return {"graph": graph, "attempts": attempts}


def select_records(records_path, splits_path, split, essays, allow_pilot_check):
    splits = json.loads(Path(splits_path).read_text())
    wanted = list(essays) if essays else list(splits[split])
    forbidden = set(splits["pilot_check"]) & set(wanted)
    if forbidden and not allow_pilot_check:
        raise SystemExit(f"Refusing pilot_check essays before prompts are frozen: {sorted(forbidden)} (use --allow-pilot-check)")
    with open(records_path) as handle:
        records = {r["example_id"]: r for r in map(json.loads, handle) if r["example_id"] in set(wanted)}
    missing = [e for e in wanted if e not in records]
    if missing:
        raise SystemExit(f"Essays not in records: {missing}")
    return [ExampleRecord.from_dict(records[e]) for e in wanted]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--split", default="development", choices=["development", "pilot_check"])
    parser.add_argument("--essay", action="append", default=[], help="Example ID (repeatable); overrides --split")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--force", action="store_true", help="Re-extract essays that already have output for this config")
    parser.add_argument("--allow-pilot-check", action="store_true")
    args = parser.parse_args()
    records = select_records(args.records, args.splits, args.split, args.essay, args.allow_pilot_check)
    key = config_hash(args.model, args.effort)
    run_dir = args.output_dir / f"{PROMPT_VERSION.replace('/', '-')}_{args.model}_{args.effort}_{key}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "system_prompt.txt").write_text(system_prompt())
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "prompt_version": PROMPT_VERSION, "config_hash": key, "model": args.model, "effort": args.effort,
        "schema_version": SCHEMA_VERSION, "records": str(args.records),
        "records_sha256": hashlib.sha256(args.records.read_bytes()).hexdigest(), "essays": {}}
    caller = AnthropicCaller(args.model, args.effort)
    for record in records:
        name = record.example_id.replace("persuade:", "")
        graph_path, log_path = run_dir / f"{name}.graph.json", run_dir / f"{name}.log.json"
        if graph_path.exists() and not args.force:
            print(f"{name}: cached")
            continue
        attempts = []
        try:
            result = extract(record, caller, args.max_attempts, attempts)
        except Exception as exc:  # one essay's API or parsing error must not end the batch or lose its log
            attempts.append({"stage": "error", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
            result = {"graph": None, "failed_stage": "error", "attempts": attempts}
        log_path.write_text(json.dumps(result["attempts"], indent=2, ensure_ascii=False, default=str))
        usage = [a.get("usage", {}) for a in result["attempts"]]
        status = {"status": "ok" if result["graph"] else f"failed_{result['failed_stage']}",
                  "attempts": len(result["attempts"]),
                  "input_tokens": sum(u.get("input_tokens", 0) for u in usage),
                  "output_tokens": sum(u.get("output_tokens", 0) for u in usage)}
        if result["graph"]:
            graph = result["graph"]
            graph["provenance"] = {"annotator": f"{args.model} ({PROMPT_VERSION}, effort {args.effort})",
                                   "review_status": "not_human_reviewed", "config_hash": key}
            graph_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False))
            status.update(units=len(graph["units"]), relations=len(graph["relations"]), derived=len(argument_edges(graph)))
        manifest["essays"][record.example_id] = status
        manifest_path.write_text(json.dumps(manifest, indent=2))
        print(f"{name}: {status}")


if __name__ == "__main__":
    main()
