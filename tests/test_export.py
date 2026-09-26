import unittest
import xml.etree.ElementTree as ET

from ling_mapper.export_gephi import GEXF, build
from ling_mapper.render_html import render
from ling_mapper import render_graph_html


def span(aid, start, text, role):
    return dict(annotation_id=aid, start=start, end=start + len(text), text=text, role=role)


class GephiExportTests(unittest.TestCase):
    def test_nodes_edges_and_unannotated_filter(self):
        record = dict(example_id="e", metadata={"holistic_score": "3", "hierarchy_candidates": [
            {"annotation_id": "c", "candidate_parent_ids": ["p"], "status": "unique_candidate"},
            {"annotation_id": "u", "candidate_parent_ids": ["p"], "status": "unique_candidate"},
            {"annotation_id": "c", "candidate_parent_ids": ["p", "x"], "status": "ambiguous"}]},
            gold_spans=[span("p", 0, "Keep it.", "position"), span("c", 9, "It works.", "claim"),
                        span("u", 19, "So", "unannotated")])
        tree, n_nodes, n_edges = build([record])
        root = ET.fromstring(ET.tostring(tree.getroot()))
        ids = {n.get("id") for n in root.iter(f"{{{GEXF}}}node")}
        self.assertEqual((ids, n_nodes, n_edges), ({"p", "c"}, 2, 1))
        edge = next(root.iter(f"{{{GEXF}}}edge"))
        self.assertEqual((edge.get("source"), edge.get("target")), ("c", "p"))
        self.assertEqual(build([record], include_unannotated=True)[1:], (3, 2))
        pos = {n.get("id"): n.find("{http://gexf.net/1.3/viz}position") for n in root.iter(f"{{{GEXF}}}node")}
        self.assertGreater(float(pos["p"].get("y")), float(pos["c"].get("y")))  # parent above child
        self.assertTrue(next(root.iter(f"{{{GEXF}}}node")).get("label").startswith("POSITION: "))


class HtmlViewerTests(unittest.TestCase):
    def test_text_cannot_close_script_and_links_nest(self):
        record = dict(example_id="e", prompt="Q", response_text="Keep. </script><b>x",
                      metadata={"holistic_score": "3", "hierarchy_candidates": [
                          {"annotation_id": "c", "candidate_parent_ids": ["p"], "status": "unique_candidate"}]},
                      gold_spans=[span("p", 0, "Keep.", "position"), span("c", 6, "</script><b>x", "claim")])
        page = render([record])
        self.assertEqual(page.count("</script>"), 1)
        self.assertIn('"parent": "p"', page)



class ArgumentGraphViewerTests(unittest.TestCase):
    def test_embeds_validation_errors_and_escapes_text(self):
        text = "Keep it. </script>"
        record = dict(example_id="e", prompt="Q", response_text=text, metadata={})
        graph = {"schema_version": "argument_graph/0.1", "example_id": "e", "root": "u1", "units": [
            dict(id="u1", start=0, end=8, text="Keep it.", role="position", stance="endorsed", polarity="positive")],
            "relations": []}
        page = render_graph_html.render([(graph, record)])
        self.assertEqual(page.count("</script>"), 1)
        self.assertIn("is not covered by any unit", page)  # the uncovered '</script>' is reported, not hidden


if __name__ == "__main__":
    unittest.main()
