import unittest

from argument_graph.graph_schema import SCHEMA_VERSION, argument_edges, validate_graph

TEXT = ("I favor keeping the college instead of changing to popular vote because it is fair. "
        "A dispute is possible, but it is less likely. For example, Obama got 61.7 percent.")


def unit(uid, quote, role, stance="endorsed"):
    start = TEXT.index(quote)
    return dict(id=uid, start=start, end=start + len(quote), text=quote, role=role, stance=stance, polarity="positive")


def signal(quote, kind="dm"):
    start = TEXT.index(quote)
    return dict(type=kind, start=start, end=start + len(quote), text=quote)


def rel(rid, source, target, label, signals=None, tier="primary"):
    r = dict(id=rid, source=source, target=target, label=label, tier=tier, signals=signals or [])
    if not signals:
        r["implicit"] = True
    return r


def graph():
    return dict(schema_version=SCHEMA_VERSION, root="u1", units=[
        unit("u1", "I favor keeping the college", "position"),
        unit("u2", "instead of changing to popular vote", "position", "rejected"),
        unit("u3", "because it is fair.", "position"),
        unit("u4", "A dispute is possible,", "claim", "conceded"),
        unit("u5", "but it is less likely.", "claim"),
        unit("u6", "For example, Obama got 61.7 percent.", "evidence"),
    ], relations=[
        rel("r1", "u2", "u1", "adversative-antithesis", [signal("instead of")]),
        rel("r2", "u3", "u1", "explanation-justify", [signal("because")]),
        rel("r3", "u4", "u5", "adversative-concession", [signal("but")]),
        rel("r4", "u5", "u1", "explanation-justify"),
        rel("r5", "u6", "u5", "explanation-evidence", [signal("For example")]),
    ])


class GraphContractTests(unittest.TestCase):
    def assertError(self, g, fragment):
        errors = validate_graph(g, TEXT)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_worked_example_is_valid(self):
        self.assertEqual(validate_graph(graph(), TEXT), [])

    def test_units_must_tile_text(self):
        g = graph(); g["units"].pop(2); g["relations"].pop(1)
        self.assertError(g, "is not covered")
        g = graph(); g["units"][1]["start"] -= 3; g["units"][1]["text"] = TEXT[g["units"][1]["start"]:g["units"][1]["end"]]
        self.assertError(g, "overlaps")

    def test_quotes_must_match_offsets(self):
        g = graph(); g["units"][0]["text"] = "I favour keeping the college"
        self.assertError(g, "does not equal source slice")
        g = graph(); g["relations"][0]["signals"][0]["end"] += 1
        self.assertError(g, "signal 0: text does not equal")

    def test_primary_tree(self):
        g = graph(); g["relations"].append(rel("r6", "u2", "u5", "elaboration-additional"))
        self.assertError(g, "more than one primary head")
        g = graph(); g["relations"].pop(3)
        self.assertError(g, "units without a head: ['u1', 'u5']")
        g = graph(); g["relations"].append(rel("r6", "u1", "u6", "elaboration-additional"))
        self.assertError(g, "primary cycle")

    def test_edges_need_signal_or_explicit_implicit(self):
        g = graph(); del g["relations"][3]["implicit"]
        self.assertError(g, "needs a quoted signal or implicit=true")
        g = graph(); g["relations"].append(rel("r6", "u6", "u1", "explanation-evidence", tier="secondary"))
        self.assertError(g, "secondary edges must be licensed")

    def test_secondary_edge_with_signal_is_allowed_but_not_duplicate(self):
        g = graph(); g["relations"].append(rel("r6", "u6", "u1", "explanation-evidence", [signal("For example")], "secondary"))
        self.assertEqual(validate_graph(g, TEXT), [])
        g = graph(); g["relations"].append(rel("r6", "u6", "u5", "explanation-evidence", [signal("For example")], "secondary"))
        self.assertError(g, "duplicates a primary edge")

    def test_inventory_and_multinuclear_direction(self):
        g = graph(); g["relations"][4]["label"] = "supports"
        self.assertError(g, "not in inventory")
        g = graph(); g["relations"][2]["label"] = "adversative-contrast"
        self.assertError(g, "multinuclear chain")

    def test_extended_inventory_labels_are_accepted(self):
        for label in ("mode-means", "topic-solutionhood", "topic-question", "organization-phatic"):
            g = graph(); g["relations"][3]["label"] = label
            self.assertEqual(validate_graph(g, TEXT), [], label)

    def test_same_unit_joins_parts_around_an_interruption(self):
        text = "The system induces candidates-as we saw in 2012-to focus on swing states."
        def u(uid, quote, role="claim"):
            a = text.index(quote); return dict(id=uid, start=a, end=a + len(quote), text=quote, role=role, stance="endorsed", polarity="positive")
        g = dict(schema_version=SCHEMA_VERSION, root="p1", units=[
            u("p1", "The system induces candidates"), u("aside", "-as we saw in 2012-", "evidence"),
            u("p2", "to focus on swing states.")], relations=[
            dict(id="r1", source="p2", target="p1", label="same-unit", tier="primary", signals=[], implicit=True),
            dict(id="r2", source="aside", target="p1", label="explanation-evidence", tier="primary",
                 signals=[dict(type="lexical", start=text.index("as we saw"), end=text.index("as we saw") + 9, text="as we saw")])])
        self.assertEqual(validate_graph(g, text), [])
        self.assertEqual([(e["type"], e["source"]) for e in argument_edges(g)], [("support", "aside")])
        g["relations"][0].update(source="aside", target="p1"); g["relations"][1].update(source="p2")
        self.assertTrue(any("separated by an interrupting unit" in e for e in validate_graph(g, text)))

    def test_problem_supports_its_solution(self):
        g = graph(); g["relations"][4]["label"] = "topic-solutionhood"
        edges = {(e["type"], e["source"], e["target"], e["basis"]) for e in argument_edges(g)}
        self.assertIn(("support", "u6", "u5", "problem-solution"), edges)

    def test_stance_must_match_adversative_structure(self):
        g = graph(); g["units"][3]["stance"] = "endorsed"
        self.assertError(g, "adversative-concession satellite must have stance 'conceded'")
        g = graph(); g["units"][1]["stance"] = "conceded"
        self.assertError(g, "adversative-antithesis satellite must have stance 'rejected'")
        g = graph(); g["units"][5]["stance"] = "rejected"
        self.assertError(g, "unit u6: stance 'rejected' needs an adversative relation")

    def test_support_and_attack_are_derived_from_stance(self):
        edges = {(e["type"], e["source"], e["target"]) for e in argument_edges(graph())}
        self.assertEqual(edges, {("support", "u3", "u1"), ("support", "u5", "u1"), ("support", "u6", "u5"),
                                 ("attack", "u1", "u2"), ("attack", "u5", "u4")})
        g = graph(); g["units"][5]["stance"] = "rejected"  # evidence the writer rejects supports nothing
        self.assertNotEqual(validate_graph(g, TEXT), [])  # and is invalid without an adversative relation
        self.assertNotIn(("support", "u6", "u5"), {(e["type"], e["source"], e["target"]) for e in argument_edges(g)})


if __name__ == "__main__":
    unittest.main()
