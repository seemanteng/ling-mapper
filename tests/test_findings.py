import unittest

from argument_graph.findings import build
from argument_graph.render_findings_html import render

TEXT = "Keep it.\n\nIt is fair. It is fair and stable. Some say it is bad.\n\nFacts: 538 electors."
SOURCES = {"f4": {"id": "f4", "source": "S1", "paragraph": 3, "text": "The Electoral College consists of 538 electors."},
           "q19": {"id": "q19", "source": "S3", "paragraph": 18, "text": "but it's less likely than a dispute."}}
EXPECT = {"expectations": [{"id": e, "criterion": e} for e in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")]}


def unit(uid, role, stance="endorsed"):
    return {"id": uid, "text": uid, "role": role, "stance": stance}


def rel(src, tgt, label, tier="primary"):
    return {"id": f"r_{src}", "source": src, "target": tgt, "label": label, "tier": tier}


GRAPH = {"root": "u1", "units": [unit("u1", "position"), unit("u2", "claim"), unit("u3", "claim"), unit("u4", "claim"),
                                  unit("u5", "evidence"), unit("u6", "claim"), unit("u7", "counterclaim", "reported")],
         "relations": [rel("u2", "u1", "explanation-justify"), rel("u3", "u1", "explanation-justify"),
                       rel("u4", "u3", "joint-list"), rel("u5", "u4", "explanation-evidence"),
                       rel("u6", "u2", "contingency-condition"), rel("u7", "u1", "elaboration-additional")]}
ALIGN = {"u1": {"label": "none", "source_units": []}, "u2": {"label": "none", "source_units": []},
         "u3": {"label": "none", "source_units": []}, "u4": {"label": "none", "source_units": []},
         "u5": {"label": "quote", "source_units": ["f4"]}, "u6": {"label": "none", "source_units": []},
         "u7": {"label": "distorted", "source_units": ["q19"], "note": "reversed"}}


class FindingsTests(unittest.TestCase):
    def setUp(self):
        self.report = build({"example_id": "e", "response_text": TEXT}, GRAPH, ALIGN, SOURCES, EXPECT)
        self.kinds = [(f["type"], tuple(f["units"])) for f in self.report["findings"]]

    def test_distortion_becomes_a_reviewable_misconception_candidate(self):
        f = next(f for f in self.report["findings"] if f["type"] == "possible_misconception")
        self.assertEqual((f["units"], f["source_units"], f["student_stance"], f["review_status"]), (["u7"], ["q19"], "reported", "needs_review"))
        self.assertEqual(f["source_text"][0]["paragraph"], 18)

    def test_only_reasons_without_support_are_unsupported(self):
        unsupported = [u for kind, u in self.kinds if kind == "unsupported_claim"]
        self.assertEqual(unsupported, [("u2",)])  # u3 shares u4's support; u6 is only a condition

    def test_expectations_are_checked_and_reported(self):
        self.assertEqual(self.report["expectations"]["E5"], "met")  # S1 and S3
        self.assertEqual(self.report["expectations"]["E6"], "not judged")  # too few source-based units
        self.assertEqual(self.report["expectations"]["E4"], "met")
        self.assertEqual(self.report["expectations"]["E1"], "not checked")
        one_source = dict(ALIGN, u7={"label": "none", "source_units": []})
        report = build({"example_id": "e", "response_text": TEXT}, GRAPH, one_source, SOURCES, EXPECT)
        self.assertEqual(report["expectations"]["E5"], "not met")
        self.assertIn("missing_required_content", [f["type"] for f in report["findings"]])

    def test_review_page_escapes_text(self):
        page = render([{"id": "e", "text": "</script>", "units": [], "expectations": {}, "criteria": {},
                        "source_use": {"units_per_source": {}, "source_based_units": 0}, "findings": self.report["findings"]}])
        self.assertEqual(page.count("</script>"), 1)
        self.assertIn("possible_misconception", page)


if __name__ == "__main__":
    unittest.main()
