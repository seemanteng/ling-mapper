import unittest

from argument_graph.graph_schema import validate_graph
from argument_graph.reference_graph import to_graph


def sheet(*segments):
    """segments: (text, role, stance, parent, how)."""
    return [{"essay_no": "1", "example_id": "X", "segment_no": str(i), "unit_id": f"u{i}", "segment_text": t,
             "What is the segment doing?": role, "Is this the writer's stance?": stance,
             "Segment it relates to": parent, "How it relates": how}
            for i, (t, role, stance, parent, how) in enumerate(segments, 1)]


def build(*segments):
    rows = sheet(*segments)
    text = " ".join(r["segment_text"] for r in rows)
    graph = to_graph("persuade:X", text, rows)
    return graph, validate_graph(graph, text)


def edges(graph):
    return {(r["source"], r["target"]): r["label"] for r in graph["relations"]}


class ReferenceGraphTest(unittest.TestCase):
    def test_support_labels_depend_on_the_target_role(self):
        graph, errors = build(("We need it.", "Position", "Endorsed", "TOP", ""),
                              ("It saves time.", "Claim", "Endorsed", "s1", "backs it up"),
                              ("Buses are slow.", "Evidence", "Endorsed", "s2", "backs it up"),
                              ("For example, mine is.", "Evidence", "Endorsed", "s3", "gives an example"))
        self.assertEqual(errors, [])
        self.assertEqual(edges(graph), {("u2", "u1"): "explanation-justify", ("u3", "u2"): "explanation-justify",
                                        ("u4", "u3"): "explanation-evidence"})
        self.assertEqual(graph["root"], "u1")

    def test_counterclaim_becomes_satellite_of_its_reply(self):
        graph, errors = build(("Keep it.", "Position", "Endorsed", "TOP", ""),
                              ("Some say no,", "Counterclaim", "Conceded", "s1", "argues against it"),
                              ("but they are wrong.", "Rebuttal", "Endorsed", "s2", "argues against it"),
                              ("A fact.", "Evidence", "Endorsed", "s3", "backs it up"))
        self.assertEqual(errors, [])
        self.assertEqual(edges(graph), {("u3", "u1"): "explanation-justify", ("u2", "u3"): "adversative-concession",
                                        ("u4", "u3"): "explanation-evidence"})

    def test_fronted_contrast_moves_the_earlier_member_up(self):
        graph, errors = build(("Keep it.", "Position", "Endorsed", "TOP", ""),
                              ("It is cheap.", "Claim", "Endorsed", "s1", "backs it up"),
                              ("Some like cars,", "Evidence", "Reported", "s4", "contrasts with it"),
                              ("others like trains.", "Evidence", "Endorsed", "s2", "backs it up"))
        self.assertEqual(errors, [])
        self.assertEqual(edges(graph)[("u4", "u3")], "adversative-contrast")
        self.assertEqual(edges(graph)[("u3", "u2")], "explanation-justify")

    def test_contrast_to_the_position_falls_back_to_background(self):
        graph, errors = build(("Although some may disagree,", "Lead", "Reported", "s2", "contrasts with it"),
                              ("online is better.", "Position", "Endorsed", "TOP", ""))
        self.assertEqual(errors, [])
        self.assertEqual(edges(graph), {("u1", "u2"): "context-background"})

    def test_text_not_in_the_essay_is_an_error(self):
        rows = sheet(("Keep it.", "Position", "Endorsed", "TOP", ""))
        with self.assertRaises(ValueError):
            to_graph("persuade:X", "Something else.", rows)


if __name__ == "__main__":
    unittest.main()
