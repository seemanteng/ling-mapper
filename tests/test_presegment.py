import tempfile
import unittest
from pathlib import Path

from argument_graph.presegment import presegment, write_sheets
from argument_graph.schemas import ExampleRecord


def pieces(text):
    return [text[a:b] for a, b in presegment(text)]


class PresegmentTest(unittest.TestCase):
    def test_segments_tile_the_text(self):
        text = "I agree.  Students save time, and they sleep more;\n\nbut some get lonely because nobody is there."
        spans = presegment(text)
        covered = list(text)
        for a, b in spans:
            covered[a:b] = " " * (b - a)
        self.assertEqual("".join(covered).strip(), "")
        self.assertTrue(all(b <= c for (_, b), (c, _) in zip(spans, spans[1:])))

    def test_clause_markers_and_lists(self):
        self.assertEqual(pieces("Students save time, and they sleep more because school starts late."),
                         ["Students save time,", "and they sleep more", "because school starts late."])
        self.assertEqual(pieces("It improves participation, attendance, and grades."),
                         ["It improves participation, attendance, and grades."])
        self.assertEqual(pieces("If students are sick, they can still attend class."),
                         ["If students are sick,", "they can still attend class."])

    def test_abbreviations_and_short_pieces(self):
        self.assertEqual(pieces("Dr. Smith agrees with this plan. But not really."),
                         ["Dr. Smith agrees with this plan.", "But not really."])
        self.assertEqual(pieces("Games, pets, etc. Then the work suffers."),
                         ["Games, pets, etc.", "Then the work suffers."])

    def test_cause_splits_only_as_connective(self):
        self.assertEqual(pieces("Such a gap can cause a student to feel stranded at home."),
                         ["Such a gap can cause a student to feel stranded at home."])
        self.assertEqual(pieces("Being home schooled is nice cause you can do whatever you want."),
                         ["Being home schooled is nice", "cause you can do whatever you want."])

    def test_long_run_on_splits_before_subject(self):
        run_on = ("students would have more time to do there work at home with no teacher around to help "
                  "them out at all during the whole day and they wouldnt feel rushed to finish the work")
        self.assertEqual(len(pieces(run_on)), 2)

    def test_sheets_number_essays_in_order(self):
        records = [ExampleRecord(f"persuade:E{i}", "q", "First point here. Second point here.",
                                 metadata={"original_id": f"E{i}", "holistic_score": "3"}) for i in (1, 2)]
        with tempfile.TemporaryDirectory() as tmp:
            index = write_sheets(Path(tmp), records)
            sheet = (Path(tmp) / "Essay 2.csv").read_text().splitlines()
        self.assertEqual([row["segments"] for row in index], [2, 2])
        self.assertTrue(sheet[1].startswith("2,E2,1,u1,First point here."))
        self.assertIn("Overall Essay Comments", sheet[-2])


if __name__ == "__main__":
    unittest.main()
