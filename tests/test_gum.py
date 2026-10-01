import tempfile
import unittest
from pathlib import Path

from argument_graph.evaluate import against_gold_graph
from argument_graph.loaders.gum import convert

CONLLU = """# newdoc id = GUM_letter_test
# meta::genre = letter
# meta::title = A test letter
# newpar
# text = Dear Sam:
1\tDear\t_\t_\t_\t_\t_\t_\t_\t_
# newpar
# text = We won't go, because it rains.
1\tWe\t_\t_\t_\t_\t_\t_\t_\t_
"""
RSD = "\n".join([
    "1\tDear Sam :\t0\t_\t_\t_\t2\torganization-preparation_r\t_\t_",
    "2\tWe wo n't go ,\t0\t_\t_\t_\t0\tROOT\t_\t_",
    "3\tbecause it rains .\t0\t_\t_\t_\t2\texplanation-justify_r\t1:elaboration-additional_r:1:1:_\t_",
]) + "\n"


class GumLoaderTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "dep").mkdir()
        (self.dir / "rst" / "dependencies").mkdir(parents=True)
        (self.dir / "dep" / "GUM_letter_test.conllu").write_text(CONLLU)
        (self.dir / "rst" / "dependencies" / "GUM_letter_test.rsd").write_text(RSD)

    def test_convert_offsets_tree_and_labels(self):
        record, gold = convert(self.dir, "GUM_letter_test")
        self.assertEqual(record.response_text, "Dear Sam:\n\nWe won't go, because it rains.")
        self.assertEqual([u["text"] for u in gold["units"]], ["Dear Sam:", "We won't go,", "because it rains."])
        self.assertEqual(gold["root"], "u2")
        primary = {(r["source"], r["target"], r["label"]) for r in gold["relations"] if r["tier"] == "primary"}
        self.assertEqual(primary, {("u1", "u2", "organization-preparation"), ("u3", "u2", "explanation-justify")})
        self.assertIn(("u3", "u1", "elaboration-additional"),
                      {(r["source"], r["target"], r["label"]) for r in gold["relations"] if r["tier"] == "secondary"})

    def test_gold_scores_perfectly_against_itself_without_roles(self):
        record, gold = convert(self.dir, "GUM_letter_test")
        m = against_gold_graph(record.response_text, gold, gold)
        self.assertEqual(m["attachment"]["labelled_accuracy"], 1.0)
        self.assertIsNone(m["role_agreement"])
        self.assertIsNone(m["derived_edges"])

    def test_missing_token_fails(self):
        (self.dir / "rst" / "dependencies" / "GUM_letter_test.rsd").write_text(RSD.replace("rains", "pours"))
        with self.assertRaises(ValueError):
            convert(self.dir, "GUM_letter_test")


if __name__ == "__main__":
    unittest.main()
