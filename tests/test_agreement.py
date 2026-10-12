import csv
import tempfile
import unittest
from pathlib import Path

from argument_graph.agreement import choose_essays, cohen_kappa, score, write_blank_sheets
from argument_graph.presegment import SHEET_COLUMNS

TEXT = "Keep it. It is cheap. But some disagree."
ROLE, STANCE, PARENT, HOW = SHEET_COLUMNS[5:9]


def write_sheet(path, labels):
    segments = ["Keep it.", "It is cheap.", "But some disagree."]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SHEET_COLUMNS)
        for n, (text, lab) in enumerate(zip(segments, labels), 1):
            writer.writerow([1, "X", n, f"u{n}", text, *lab, ""])


FINAL = [("Position", "Endorsed", "TOP", ""), ("Claim", "Endorsed", "s1", "backs it up"),
         ("Counterclaim", "Conceded", "s1", "argues against it")]
RECORDS = {"persuade:X": {"response_text": TEXT, "metadata": {"holistic_score": "3"}}}


class AgreementTest(unittest.TestCase):
    def test_kappa(self):
        self.assertEqual(cohen_kappa([("a", "a"), ("b", "b")]), 1.0)
        self.assertAlmostEqual(cohen_kappa([("a", "b"), ("b", "a")]), -1.0)
        self.assertEqual(cohen_kappa([("a", "a")] * 3), 1.0)
        self.assertIsNone(cohen_kappa([]))

    def test_blank_sheets_keep_the_segments_and_drop_every_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            final, blank = Path(tmp) / "final", Path(tmp) / "blank"
            final.mkdir()
            write_sheet(final / "Essay 1.csv", FINAL)
            write_blank_sheets(final, blank, [1], RECORDS)
            rows = list(csv.DictReader((blank / "Essay 1.csv").open()))
            segments = [r for r in rows if r["segment_text"]]
            self.assertEqual([r["segment_text"] for r in segments], ["Keep it.", "It is cheap.", "But some disagree."])
            self.assertTrue(all(not r[ROLE] and not r[STANCE] and not r[PARENT] and not r[HOW] for r in rows))
            self.assertEqual(choose_essays(final, RECORDS, min_segments=1)[0][:2], ("3", 1))

    def test_identical_labels_agree_and_a_changed_label_shows(self):
        with tempfile.TemporaryDirectory() as tmp:
            final, new = Path(tmp) / "final", Path(tmp) / "new"
            final.mkdir(), new.mkdir()
            write_sheet(final / "Essay 1.csv", FINAL)
            write_sheet(new / "Essay 1.csv", FINAL)
            text, problems = score(final, new, RECORDS)
            self.assertEqual(problems, {})
            self.assertIn("| role | 1.000 | 1.000 |", text)
            changed = [FINAL[0], ("Evidence", "Endorsed", "s1", "backs it up"), FINAL[2]]
            write_sheet(new / "Essay 1.csv", changed)
            text, _ = score(final, new, RECORDS)
            self.assertIn("| role | 0.667 |", text)

    def test_unfinished_and_edited_sheets_are_reported_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            final, new = Path(tmp) / "final", Path(tmp) / "new"
            final.mkdir(), new.mkdir()
            write_sheet(final / "Essay 1.csv", FINAL)
            write_sheet(new / "Essay 1.csv", [("", "", "", "")] * 3)
            _, problems = score(final, new, RECORDS)
            self.assertIn("no role", problems[1][0])


if __name__ == "__main__":
    unittest.main()
