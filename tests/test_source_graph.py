import unittest

from argument_graph.render_source_html import render
from argument_graph.source_graph import build_source_graph

TEXT = "Keep the system. It is stable.\n\nSome say it is unfair. It is not democratic, but it works. Why?"
RECORD = {"example_id": "source:T", "response_text": TEXT,
          "metadata": {"source_id": "T", "title": "t", "author": "a", "paragraphs": {"1": [0, 30], "2": [32, len(TEXT)]}}}
UNITS = [("t1", "Keep the system.", "thesis", "endorsed"), ("t2", "It is stable.", "claim", "endorsed"),
         ("t3", "Some say it is unfair.", "opposing_view", "reported"),
         ("t4", "It is not democratic,", "concession", "conceded"), ("t5", "but it works.", "claim", "endorsed"),
         ("t6", "Why?", "framing", "endorsed")]
EDGES = [("supports", ["t2"], "t1", None), ("opposes", ["t4", "t5"], "t3", None),
         ("concedes", ["t4"], "t5", None), ("supports", ["t5"], "t1", None)]


class SourceGraphTests(unittest.TestCase):
    def test_valid_graph_records_paragraphs(self):
        graph, errors = build_source_graph(RECORD, UNITS, EDGES)
        self.assertEqual(errors, [])
        self.assertEqual([u["paragraph"] for u in graph["units"]], [1, 1, 2, 2, 2, 2])

    def test_passage_edges_cover_every_unit_in_them(self):
        graph, _ = build_source_graph(RECORD, UNITS, EDGES)
        self.assertEqual(graph["edges"][1]["from"], ["t4", "t5"])

    def test_type_and_stance_must_agree(self):
        units = [u if u[0] != "t4" else ("t4", u[1], "concession", "endorsed") for u in UNITS]
        _, errors = build_source_graph(RECORD, units, EDGES)
        self.assertTrue(any("must have stance conceded" in e for e in errors))

    def test_edge_targets_are_checked(self):
        _, errors = build_source_graph(RECORD, UNITS, EDGES + [("supports", ["t2"], "t6", None), ("opposes", ["t2"], "t1", None)])
        self.assertTrue(any("supports must point to a thesis or claim" in e for e in errors))
        self.assertTrue(any("opposes must point to an opposing_view" in e for e in errors))

    def test_opinion_source_leaves_no_unit_unlinked_but_a_fact_sheet_may(self):
        _, errors = build_source_graph(RECORD, UNITS, EDGES[:1] + EDGES[2:])
        self.assertTrue(any("opposing view is not answered" in e for e in errors))
        facts = [(uid, q, "framing" if kind == "framing" else "fact", "endorsed") for uid, q, kind, _ in UNITS]
        self.assertEqual(build_source_graph(RECORD, facts, [])[1], [])

    def test_uncovered_text_is_reported(self):
        _, errors = build_source_graph(RECORD, UNITS[:-1], EDGES)
        self.assertTrue(any("not covered" in e for e in errors))

    def test_viewer_escapes_text_and_lists_errors(self):
        record = dict(RECORD, response_text=TEXT.replace("Why?", "</script>"))
        units = UNITS[:-1] + [("t6", "</script>", "framing", "endorsed")]
        graph, _ = build_source_graph(record, units, EDGES)
        graph["units"][0]["type"] = "bogus"
        page = render([(graph, record)])
        self.assertEqual(page.count("</script>"), 1)
        self.assertIn("unknown type", page)


if __name__ == "__main__":
    unittest.main()
