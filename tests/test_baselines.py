import unittest

from argument_graph.baselines import majority_graph, rules_graph
from argument_graph.graph_schema import validate_graph

TEXT = ("Schools are changing quickly. I think students should learn at home because it saves time, "
        "but some get lonely.\n\nFor example, my cousin sleeps more.\n\nIn conclusion, home is better.")


class BaselineTest(unittest.TestCase):
    def test_both_baselines_are_valid_graphs(self):
        for build in (majority_graph, rules_graph):
            self.assertEqual(validate_graph(build("persuade:X", TEXT), TEXT), [])

    def test_majority_attaches_everything_to_the_first_unit(self):
        graph = majority_graph("persuade:X", TEXT)
        self.assertEqual(graph["root"], "u1")
        self.assertTrue(all(r["target"] == "u1" for r in graph["relations"]))
        self.assertEqual({u["role"] for u in graph["units"][1:]}, {"evidence"})

    def test_rules_find_the_thesis_and_label_by_connective(self):
        graph = rules_graph("persuade:X", TEXT)
        units = {u["id"]: u for u in graph["units"]}
        root = units[graph["root"]]
        self.assertIn("I think", root["text"])
        self.assertEqual(root["role"], "position")
        self.assertEqual(units["u1"]["role"], "lead")
        rel = {units[r["source"]]["text"]: r for r in graph["relations"]}
        self.assertEqual(rel["Schools are changing quickly."]["label"], "context-background")
        self.assertEqual(rel["but some get lonely."]["label"], "adversative-contrast")
        self.assertEqual(rel["For example, my cousin sleeps more."]["label"], "explanation-evidence")
        self.assertEqual(units[rel["In conclusion, home is better."]["source"]]["role"], "concluding_summary")


if __name__ == "__main__":
    unittest.main()
