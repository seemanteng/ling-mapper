import csv
import json
import tempfile
import unittest
from pathlib import Path

from argument_graph.loaders.persuade import load_persuade
from argument_graph.prepare_data import select_pilot
from argument_graph.schemas import ExampleRecord, GoldSpan, SourcePassage
from argument_graph.spans import recover_span


class SpanTests(unittest.TestCase):
    def test_inclusive(self):
        span = recover_span("Hello world", "Hello", "0", "4")
        self.assertEqual((span.start, span.end, span.method), (0, 5, "inclusive_exact"))

    def test_repeated_text_is_not_guessed(self):
        self.assertEqual(recover_span("yes and yes", "yes", "20", "25").reason, "ambiguous_exact_text")
        self.assertEqual(recover_span("yes and yes", "yes", "8", "11").start, 8)

    def test_normalised_offsets_map_to_original_unicode_text(self):
        text = "α Before\n\t many  spaces. Ω"
        span = recover_span(text, "Before many spaces.", "99", "120")
        self.assertEqual(text[span.start:span.end], "Before\n\t many  spaces.")
        self.assertEqual(span.method, "unique_whitespace_normalised")

    def test_unrecoverable_and_empty(self):
        self.assertEqual(recover_span("abc", "xyz", "0", "3").reason, "text_not_found")
        self.assertIsNone(recover_span("abc", "  ", "0", "1").start)


class RecordTests(unittest.TestCase):
    def test_roundtrip_and_no_gold_leakage(self):
        r = ExampleRecord("x", "Question", "Claim", source_passages=[SourcePassage("s", "Source")],
                          gold_spans=[GoldSpan("a", "x", 0, 5, "Claim", "Claim", "claim")],
                          metadata={"holistic_score": 1, "unresolved_annotations": ["secret"]})
        restored = ExampleRecord.from_dict(r.to_dict())
        self.assertEqual(restored.to_dict(), r.to_dict())
        self.assertEqual(set(restored.model_input()), {"prompt", "response_text", "source_passages", "rubric"})
        self.assertNotIn("secret", json.dumps(restored.model_input()))

    def test_bad_span_rejected(self):
        r = ExampleRecord("x", "q", "abc", gold_spans=[GoldSpan("a", "x", 0, 2, "abc", "Claim", "claim")])
        with self.assertRaises(ValueError):
            r.validate()

    def test_annotation_absence_distinct_from_empty(self):
        self.assertIsNone(ExampleRecord("x", "q", "a").to_dict()["gold_spans"])
        self.assertEqual(ExampleRecord("x", "q", "a", gold_spans=[]).to_dict()["gold_spans"], [])


class LoaderTests(unittest.TestCase):
    def fixture(self, path, rows):
        fields = sorted(set().union(*(row.keys() for row in rows)))
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def row(self, **changes):
        row = dict(essay_id_comp="e1", full_text="Yes. No.", assignment="Discuss", prompt_name="Topic",
                   competition_set="train", holistic_essay_score="3", source_text="Article title",
                   discourse_id="1E+12", discourse_start="0", discourse_end="4", discourse_text="Yes.",
                   discourse_type="Claim", discourse_effectiveness="Adequate")
        return {**row, **changes}

    def test_collision_recovery_join_and_hierarchy(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "train.csv"
            self.fixture(path, [self.row(), self.row(discourse_start="5", discourse_end="8", discourse_text="No.",
                          discourse_type="Counterclaim", hierarchical_id="1E+12", hierarchical_text="Yes.", hierarchical_label="Claim")])
            holistic = Path(d) / "holistic.csv"
            self.fixture(holistic, [dict(essay_id_comp="other", full_text="other")])
            records, report = load_persuade(path, holistic_path=holistic)
            r = records[0]
            self.assertEqual(len({x.annotation_id for x in r.gold_spans}), 2)
            self.assertEqual(report["missing_supplementary_essay_ids"], ["e1"])
            self.assertEqual(r.metadata["hierarchy_candidates"][0]["status"], "unique_candidate")
            self.assertIsNone(r.gold_relations)
            self.assertIsNone(r.source_passages)
            self.assertEqual(r.metadata["source_citations"], "Article title")

    def test_unresolved_quarantined(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "train.csv"
            self.fixture(path, [self.row(discourse_text="Not in essay")])
            records, report = load_persuade(path)
            self.assertEqual(records[0].gold_spans, [])
            self.assertEqual(len(records[0].metadata["unresolved_annotations"]), 1)
            self.assertEqual(report["recovery_methods"], {"unresolved": 1})

    def test_unannotated_fragment_inside_labelled_span_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "train.csv"
            self.fixture(path, [self.row(),
                                self.row(discourse_start="1", discourse_end="3", discourse_text="es", discourse_type="Unannotated"),
                                self.row(discourse_start="5", discourse_end="8", discourse_text="No.", discourse_type="Unannotated")])
            records, report = load_persuade(path)
            self.assertEqual([g.text for g in records[0].gold_spans], ["Yes.", "No."])
            self.assertEqual(report["unresolved_reasons"], {"unannotated_overlaps_labelled": 1})

    def test_holistic_only_and_dataset_independent_projection(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "holistic.csv"
            self.fixture(path, [dict(essay_id_comp="e", full_text="Answer", assignment="Question", prompt_name="Topic")])
            records, _ = load_persuade(path)
            # A differently shaped dataset fixture maps to the same common contract.
            other = {"id": "z", "question": "Question", "answer": "Answer"}
            alternate = ExampleRecord(other["id"], other["question"], other["answer"], metadata={"dataset": "fixture"})
            self.assertEqual(records[0].model_input(), alternate.model_input())
            self.assertIsNone(records[0].gold_spans)

    def test_conflicting_text_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "train.csv"
            self.fixture(path, [self.row(), self.row(full_text="Changed")])
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                load_persuade(path)

    def test_pilot_reproducible_and_excludes_test(self):
        records = [ExampleRecord(str(i), "q", "a", metadata={"official_split": "train", "holistic_score": str(i % 3)}) for i in range(20)]
        records.append(ExampleRecord("test", "q", "a", metadata={"official_split": "test"}))
        a, split = select_pilot(records, 10, 42)
        b, split2 = select_pilot(list(reversed(records)), 10, 42)
        self.assertEqual(split, split2)
        self.assertEqual(len(split["development"]), 5)
        self.assertFalse(set(split["development"]) & set(split["pilot_check"]))
        self.assertNotIn("test", [r.example_id for r in a])

    def test_inspected_essay_leaves_pilot_check_for_same_band_replacement(self):
        records = [ExampleRecord(str(i), "q", "a", metadata={"official_split": "train", "holistic_score": str(i % 3)}) for i in range(30)]
        _, split = select_pilot(records, 10, 42)
        seen = split["pilot_check"][0]
        pilot, amended = select_pilot(records, 10, 42, [seen])
        band = {r.example_id: r.metadata["holistic_score"] for r in records}
        new = amended["check_replacements"][seen]
        self.assertIn(seen, amended["development"])
        self.assertNotIn(seen, amended["pilot_check"])
        self.assertEqual(band[new], band[seen])
        self.assertNotIn(new, split["development"] + split["pilot_check"])
        self.assertEqual((len(amended["development"]), len(amended["pilot_check"]), len(pilot)), (6, 5, 11))
        self.assertEqual(amended, select_pilot(list(reversed(records)), 10, 42, [seen])[1])


if __name__ == "__main__":
    unittest.main()
