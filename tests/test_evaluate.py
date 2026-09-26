import copy
import json
import unittest
from pathlib import Path

from ling_mapper.evaluate import against_gold_graph, against_persuade

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data/annotations/argument_graphs/E0737CDC1E99.json"
RECORDS = ROOT / "data/processed/electoral_college_v6/pilot.jsonl"


@unittest.skipUnless(GOLD.exists() and RECORDS.exists(), "gold graph and v6 records not present")
class EvaluateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gold = json.loads(GOLD.read_text())
        with RECORDS.open() as handle:
            cls.record = next(json.loads(l) for l in handle if cls.gold["example_id"] in l[:60])
        cls.text = cls.record["response_text"]

    def test_gold_against_itself_is_perfect(self):
        m = against_gold_graph(self.text, self.gold, self.gold)
        self.assertEqual(m["segmentation_exact"]["f1"], 1.0)
        self.assertEqual(m["attachment"]["accuracy"], 1.0)
        self.assertEqual(m["attachment"]["labelled_accuracy"], 1.0)
        self.assertEqual(m["derived_edges"]["f1"], 1.0)
        self.assertEqual((m["role_agreement"], m["stance_agreement"], m["root_match"]), (1.0, 1.0, True))

    def test_finer_segmentation_is_not_an_attachment_error(self):
        pred = copy.deepcopy(self.gold)
        u3 = next(u for u in pred["units"] if u["id"] == "u3")        # "because it is fair."
        cut = u3["start"] + len("because it")
        second = dict(u3, id="u3x", start=cut, end=u3["end"], text=self.text[cut:u3["end"]])
        u3.update(end=cut, text=self.text[u3["start"]:cut])
        pred["units"].append(second)
        pred["relations"].append({"id": "rx", "source": "u3x", "target": "u3", "label": "elaboration-additional",
                                  "tier": "primary", "signals": [], "implicit": True})
        m = against_gold_graph(self.text, pred, self.gold)
        self.assertLess(m["segmentation_exact"]["f1"], 1.0)
        self.assertEqual(m["attachment"]["accuracy"], 1.0)

    def test_wrong_head_and_label_are_counted(self):
        pred = copy.deepcopy(self.gold)
        r = next(r for r in pred["relations"] if r["source"] == "u11")  # evidence -> u10
        r["target"] = "u1"
        m = against_gold_graph(self.text, pred, self.gold)
        self.assertEqual(m["attachment"]["correct"], m["attachment"]["gold_edges"] - 1)

    def test_persuade_projection_runs_on_gold_graph(self):
        m = against_persuade(self.text, self.gold, self.record)
        self.assertGreater(m["role_agreement"], 0.9)  # gold units take PERSUADE roles
        self.assertGreater(m["element_f1_macro"], 0.5)


if __name__ == "__main__":
    unittest.main()
