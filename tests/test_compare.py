import unittest
from collections import Counter

from argument_graph.compare import bootstrap, class_scores, f1, headlines


def row(att=5, edges=10, root=1, role=0.8, stance=0.9, conf=None):
    return {"edges": edges, "att": att, "lab": att // 2, "cls": att, "root": root, "role": role, "stance": stance,
            "dtp": 2, "dpred": 4, "dgold": 4, "stp": 6, "spred": 8, "sgold": 8,
            "role_conf": conf or Counter(), "stance_conf": conf or Counter()}


class CompareTest(unittest.TestCase):
    def test_f1(self):
        self.assertAlmostEqual(f1(2, 4, 4), 0.5)
        self.assertEqual(f1(0, 0, 0), 0.0)

    def test_headlines_pool_counts_over_essays(self):
        h = headlines([row(att=10, edges=10), row(att=0, edges=30, root=0)])
        self.assertAlmostEqual(h["attachment"], 10 / 40)
        self.assertAlmostEqual(h["root"], 0.5)

    def test_class_scores_from_confusion(self):
        conf = Counter({("a", "a"): 8, ("a", "b"): 2, ("b", "b"): 6, ("b", "a"): 4, ("c", "c"): 0})
        scores, macro = class_scores([row(conf=conf)], "role_conf")
        self.assertAlmostEqual(scores["a"]["recall"], 0.8)
        self.assertAlmostEqual(scores["a"]["precision"], 8 / 12)
        self.assertNotIn("c", [c for c, v in scores.items() if v["gold_chars"]])
        self.assertAlmostEqual(macro, (scores["a"]["f1"] + scores["b"]["f1"]) / 2)

    def test_bootstrap_is_reproducible_and_pairs_the_runs(self):
        strong = [row(att=8) for _ in range(10)]
        weak = [row(att=2) for _ in range(10)]
        ci1, diff1 = bootstrap({"s": strong, "w": weak}, samples=200)
        ci2, diff2 = bootstrap({"s": strong, "w": weak}, samples=200)
        self.assertEqual(diff1, diff2)
        lo, hi = diff1[("s", "w")]["attachment"]
        self.assertAlmostEqual(lo, 0.6)
        self.assertAlmostEqual(hi, 0.6)


if __name__ == "__main__":
    unittest.main()
