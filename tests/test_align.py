import unittest

from argument_graph.align import baseline, check, judge, score
from test_student_graph import ScriptedCaller

SOURCES = {
    "f4": {"id": "f4", "text": "The Electoral College consists of 538 electors.", "type": "fact", "source": "S1"},
    "q19": {"id": "q19", "text": "but it's less likely than a dispute over the popular vote.", "type": "claim", "source": "S3"},
    "q61": {"id": "q61", "text": "that the method may turn off potential voters", "type": "opposing_view", "source": "S3"},
}
GRAPH = {"units": [{"id": "u1", "text": "the Electoral college consists of 538 electors."},
                   {"id": "u2", "text": "a dispute is less likely in a popular vote"},
                   {"id": "u3", "text": "I like it."}]}
RECORD = {"prompt": "Q", "response_text": "the Electoral college consists of 538 electors. a dispute is less likely in a popular vote I like it."}
GOOD = {"alignments": [{"unit": "u1", "label": "quote", "source_units": ["f4"], "note": ""},
                       {"unit": "u2", "label": "distorted", "source_units": ["q19"], "note": "reversed"},
                       {"unit": "u3", "label": "none", "source_units": [], "note": ""}]}


class AlignTests(unittest.TestCase):
    def test_check_requires_every_unit_and_valid_links(self):
        out, errors = check(GOOD, ["u1", "u2", "u3"], set(SOURCES))
        self.assertEqual(errors, [])
        bad = {"alignments": [{"unit": "u1", "label": "quote", "source_units": [], "note": ""},
                              {"unit": "u2", "label": "distorted", "source_units": ["zz"], "note": ""}]}
        _, errors = check(bad, ["u1", "u2", "u3"], set(SOURCES))
        text = " ".join(errors)
        for expected in ("needs at least one source unit", "unknown source units", "distorted needs a note", "no alignment for student units ['u3']"):
            self.assertIn(expected, text)

    def test_judge_retries_with_errors_then_accepts(self):
        bad = {"alignments": GOOD["alignments"][:2]}
        caller = ScriptedCaller(bad, GOOD)
        result = judge(RECORD, GRAPH, caller, SOURCES, "listing")
        self.assertEqual(result["alignments"]["u2"]["label"], "distorted")
        self.assertIn("no alignment for student units", caller.requests[1]["messages"][-1]["content"])
        self.assertNotIn("role", caller.requests[0]["messages"][0]["content"])  # unit texts only, no gold annotations

    def test_baseline_links_copied_text_only(self):
        out = baseline(GRAPH, SOURCES)
        self.assertEqual((out["u1"]["label"], out["u1"]["source_units"]), ("quote", ["f4"]))
        self.assertEqual(out["u3"]["label"], "none")

    def test_score_counts_links_and_distortions(self):
        gold = {k: v for k, v in check(GOOD, ["u1", "u2", "u3"], set(SOURCES))[0].items()}
        pred = dict(gold, u2={"label": "paraphrase", "source_units": ["q19"], "note": ""})
        s = score(pred, gold, SOURCES)
        self.assertEqual(s["label_accuracy"], round(2 / 3, 4))
        self.assertEqual(s["link_f1"], 1.0)
        self.assertEqual(s["distortion"], {"gold": 1, "found": 0, "false_alarms": 0})


if __name__ == "__main__":
    unittest.main()
