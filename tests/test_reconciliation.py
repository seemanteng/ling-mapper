import csv
import tempfile
import unittest
from pathlib import Path

from argument_graph.loaders.persuade import load_persuade
from argument_graph.spans import recover_sequence, displacement


def row(text, start, end):
    return dict(discourse_text=text, discourse_start=str(start), discourse_end=str(end))


class AmbiguityTests(unittest.TestCase):
    def test_nearest_requires_margin_and_distance(self):
        text = 'yes' + 'x' * 100 + 'yes'
        result, evidence = recover_sequence(text, [row('yes', 15, 18)])
        self.assertEqual((result[0].start, result[0].method), (0, 'nearest_clear'))
        self.assertEqual(displacement(result[0], row('yes', 15, 18))['start_delta'], -15)
        result, _ = recover_sequence(text, [row('yes', 51, 54)])
        self.assertIsNone(result[0].start)
        result, _ = recover_sequence('yes' + 'x' * 1000 + 'yes', [row('yes', 200, 203)])
        self.assertIsNone(result[0].start)

    def test_sequence_selects_between_independent_neighbours(self):
        text = 'yes A yes B yes'
        results, _ = recover_sequence(text, [row('A', 4, 5), row('yes', 99, 102), row('B', 10, 11)])
        self.assertEqual((results[1].start, results[1].method), (6, 'sequence_unique'))

    def test_sequence_conflict_does_not_choose_nearest(self):
        text = 'yes A B yes'
        results, _ = recover_sequence(text, [row('B', 6, 7), row('yes', 1, 4), row('A', 4, 5)])
        self.assertIsNone(results[1].start)

    def test_out_of_order_unique_match_is_rejected(self):
        text = 'A B C later'
        rows = [row('A', 0, 1), row('later', 20, 25), row('B', 2, 3), row('C', 4, 5)]
        results, evidence = recover_sequence(text, rows)
        self.assertEqual(results[1].reason, 'sequence_conflict')
        self.assertEqual(evidence[1]['decision'], 'order_conflict')
        self.assertEqual([r.start for r in results if r.start is not None], [0, 2, 4])

    def test_trimmed_match_at_offsets_beats_unique_repeat_elsewhere(self):
        text = 'Intro. It is unfair.\nMore text. It is unfair. '
        results, _ = recover_sequence(text, [row('It is unfair. ', 7, 21)])
        self.assertEqual((results[0].start, results[0].method), (7, 'offset_trimmed'))

    def test_swapped_pair_is_not_rejected(self):
        text = 'A C B D'
        results, _ = recover_sequence(text, [row('A', 0, 1), row('B', 9, 10), row('C', 9, 10), row('D', 6, 7)])
        self.assertTrue(all(r.start is not None for r in results))

    def test_offset_confirmed_span_is_not_rejected(self):
        text = 'A B C Z'
        results, _ = recover_sequence(text, [row('A', 0, 1), row('Z', 6, 7), row('B', 9, 10), row('C', 9, 10)])
        self.assertEqual(results[1].method, 'raw_exact')

    def test_new_decisions_are_not_anchors(self):
        text = 'yes' + 'x' * 100 + 'yes'
        results, evidence = recover_sequence(text, [row('yes', 15, 18), row('yes', 51, 54)])
        self.assertEqual(results[0].method, 'nearest_clear')
        self.assertIsNone(results[1].start)
        self.assertEqual(evidence[1]['anchor_indices'], [None, None])


class IdentityTests(unittest.TestCase):
    def write(self, path, rows):
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    def test_scientific_collision_separated_by_text_and_joined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [dict(essay_id_comp='1.13001E+11', full_text=t, assignment='q', prompt_name='p') for t in ['First essay', 'Second essay']]
            self.write(root/'input.csv', rows)
            self.write(root/'holistic.csv', [dict(essay_id_comp=eid, full_text=t) for eid,t in [('113001E60001','First essay'),('113001E60002','Second essay')]])
            records, report = load_persuade(root/'input.csv', holistic_path=root/'holistic.csv')
            self.assertEqual(len({r.example_id for r in records}), 2)
            self.assertTrue(all(r.example_id.startswith('persuade:text:') for r in records))
            self.assertEqual(report['raw_essay_id_collisions'], {'1.13001E+11': 2})
            self.assertEqual(report['supplementary_join_methods'], {'unique_exact_text': 2})
            records_without_join, _ = load_persuade(root/'input.csv')
            self.assertEqual([r.example_id for r in records], [r.example_id for r in records_without_join])

    def test_duplicate_text_in_supplement_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root/'input.csv', [dict(essay_id_comp='1.1E+11', full_text='Essay', assignment='q', prompt_name='p')])
            self.write(root/'holistic.csv', [dict(essay_id_comp=i, full_text='Essay') for i in ['a','b']])
            records, report = load_persuade(root/'input.csv', holistic_path=root/'holistic.csv')
            self.assertIsNone(records[0].metadata['canonical_essay_id'])
            self.assertEqual(report['supplementary_join_methods'], {'ambiguous_exact_text': 1})


if __name__ == '__main__':
    unittest.main()
