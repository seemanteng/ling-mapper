import json
import tempfile
import unittest
from pathlib import Path

from argument_graph.graph_schema import RELATIONS, validate_graph
from argument_graph.schemas import ExampleRecord, GoldSpan
from argument_graph.student_graph import extract, find_quote, locate_units, select_records, system_prompt

TEXT = "I favor keeping the college because it is fair. A dispute is possible, but it is less likely."
QUOTES = ["I favor keeping the college", "because it is fair.", "A dispute is possible,", "but it is less likely."]
RELATE = {"root": "u1", "units": [
    {"id": "u1", "role": "position", "stance": "endorsed", "polarity": "positive"},
    {"id": "u2", "role": "position", "stance": "endorsed", "polarity": "positive"},
    {"id": "u3", "role": "claim", "stance": "conceded", "polarity": "positive"},
    {"id": "u4", "role": "claim", "stance": "endorsed", "polarity": "positive"}], "relations": [
    {"source": "u2", "target": "u1", "label": "explanation-justify", "tier": "primary", "signals": [{"type": "dm", "text": "because"}]},
    {"source": "u3", "target": "u4", "label": "adversative-concession", "tier": "primary", "signals": [{"type": "dm", "text": "but"}]},
    {"source": "u4", "target": "u1", "label": "explanation-justify", "tier": "primary", "signals": []}]}


class ScriptedCaller:
    """Returns queued outputs in order and records every request."""

    def __init__(self, *outputs):
        self.outputs, self.requests = list(outputs), []

    def __call__(self, system, messages, schema):
        self.requests.append({"system": system, "messages": messages})
        data = self.outputs.pop(0)
        return data, [{"type": "text", "text": json.dumps(data)}], {"stop_reason": "end_turn" if data else "max_tokens",
                                                                   "usage": {"input_tokens": 10, "output_tokens": 5}}


def record():
    return ExampleRecord("e1", "Argue for or against.", TEXT,
                         gold_spans=[GoldSpan("g1", "e1", 0, 27, TEXT[:27], "Position", "position")],
                         metadata={"holistic_score": "5", "secret": "GOLD-ONLY"})


class ExtractorTests(unittest.TestCase):
    def test_two_stages_produce_valid_graph_without_gold_in_prompt(self):
        caller = ScriptedCaller({"units": QUOTES}, RELATE)
        result = extract(record(), caller)
        self.assertEqual(validate_graph(result["graph"], TEXT), [])
        self.assertEqual([u["text"] for u in result["graph"]["units"]], QUOTES)
        sent = json.dumps(caller.requests)
        self.assertNotIn("GOLD-ONLY", sent)
        self.assertNotIn('"holistic_score"', sent)
        self.assertEqual(len(result["attempts"]), 2)

    def test_segmentation_errors_are_fed_back_and_retried(self):
        bad = {"units": QUOTES[:1] + ["because it's fair."] + QUOTES[2:]}
        caller = ScriptedCaller(bad, {"units": QUOTES}, RELATE)
        result = extract(record(), caller)
        self.assertIsNotNone(result["graph"])
        feedback = caller.requests[1]["messages"][-1]["content"]
        self.assertIn("not an exact quote", feedback)
        self.assertIn("not covered", feedback)

    def test_invalid_relations_fail_after_bounded_attempts(self):
        broken = json.loads(json.dumps(RELATE)); broken["relations"].pop()  # u4 left without a head
        caller = ScriptedCaller({"units": QUOTES}, broken, broken)
        result = extract(record(), caller, max_attempts=2)
        self.assertIsNone(result["graph"])
        self.assertEqual(result["failed_stage"], "relate")
        self.assertTrue(any("units without a head" in e for e in result["attempts"][-1]["errors"]))

    def test_signal_must_be_quoted_from_linked_units(self):
        wrong = json.loads(json.dumps(RELATE)); wrong["relations"][0]["signals"] = [{"type": "dm", "text": "but"}]
        caller = ScriptedCaller({"units": QUOTES}, wrong, RELATE)
        result = extract(record(), caller)
        self.assertIsNotNone(result["graph"])
        self.assertTrue(any("not an exact quote inside either unit" in e for e in result["attempts"][1]["errors"]))

    def test_no_usable_output_is_a_failure_not_an_empty_graph(self):
        result = extract(record(), ScriptedCaller(None))
        self.assertIsNone(result["graph"])
        self.assertEqual(result["failed_stage"], "segment")

    def test_partial_attempts_survive_an_exception(self):
        class Exploding(ScriptedCaller):
            def __call__(self, system, messages, schema):
                if len(self.requests) == 1:
                    raise RuntimeError("connection reset")
                return super().__call__(system, messages, schema)
        attempts = []
        with self.assertRaises(RuntimeError):
            extract(record(), Exploding({"units": QUOTES}), attempts=attempts)
        self.assertEqual([a["stage"] for a in attempts], ["segment"])

    def test_locate_units_reports_gaps(self):
        units, errors = locate_units(TEXT, [QUOTES[0], QUOTES[2], QUOTES[3]])
        self.assertEqual(len(units), 3)
        self.assertTrue(any("because it is fair." in e for e in errors))

    def test_quotes_match_across_unreproducible_whitespace(self):
        text = "Keep it in the Constitution\xa0of the country. So why\xa0 not keep it"
        units, errors = locate_units(text, ["Keep it in the Constitution of the country.", "So why  not keep it"])
        self.assertEqual(errors, [])
        self.assertEqual([u["text"] for u in units], ["Keep it in the Constitution\xa0of the country.", "So why\xa0 not keep it"])
        self.assertTrue(all(text[u["start"]:u["end"]] == u["text"] for u in units))

    def test_whitespace_tolerance_does_not_invent_breaks_or_words(self):
        self.assertIsNone(find_quote("the Constitution", "the Consti tution"))
        self.assertIsNone(find_quote("the Constitution of", "the Constitution tof"))
        self.assertEqual(find_quote("a\xa0b a b", "a b"), (4, 7))

    def test_prompt_lists_every_label_from_the_contract(self):
        prompt = system_prompt()
        for label in RELATIONS:
            self.assertIn(label, prompt)

    def test_pilot_check_essays_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            splits = Path(d) / "splits.json"
            splits.write_text(json.dumps({"development": ["e1"], "pilot_check": ["e2"]}))
            recs = Path(d) / "records.jsonl"
            recs.write_text("\n".join(json.dumps(ExampleRecord(e, "q", "a").to_dict()) for e in ("e1", "e2")) + "\n")
            self.assertEqual([r.example_id for r in select_records(recs, splits, "development", [], False)], ["e1"])
            with self.assertRaises(SystemExit):
                select_records(recs, splits, "development", ["e2"], False)


if __name__ == "__main__":
    unittest.main()
