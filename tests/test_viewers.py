import unittest

from ling_mapper.render_html import render
from ling_mapper import render_graph_html


def span(aid, start, text, role):
    return dict(annotation_id=aid, start=start, end=start + len(text), text=text, role=role)


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
