import unittest

from argument_graph.schemas import ExampleRecord
from argument_graph.select_batch import select_batch


def record(example_id, score):
    return ExampleRecord(example_id, "q", "a", metadata={"holistic_score": score})


class SelectBatchTest(unittest.TestCase):
    def setUp(self):
        self.existing = [record("e1", "1"), record("e2", "2"), record("e3", "2")]
        self.pool = [record(f"p{band}{i}", band) for band in "12" for i in range(5)] + self.existing

    def test_tops_up_bands_and_skips_existing(self):
        selected, quotas = select_batch(self.pool, self.existing, 3, 42)
        self.assertEqual(quotas, {"1": 2, "2": 1})
        self.assertEqual([r.metadata["holistic_score"] for r in selected], ["1", "1", "2"])
        self.assertFalse({r.example_id for r in selected} & {"e1", "e2", "e3"})

    def test_reproducible_and_seed_dependent(self):
        ids = lambda seed: [r.example_id for r in select_batch(self.pool, self.existing, 3, seed)[0]]
        self.assertEqual(ids(42), ids(42))
        self.assertNotEqual({tuple(ids(s)) for s in range(10)}, {tuple(ids(42))})

    def test_rejects_short_band_and_overfull_band(self):
        with self.assertRaises(ValueError):
            select_batch(self.pool, self.existing, 9, 42)
        with self.assertRaises(ValueError):
            select_batch(self.pool, self.existing, 1, 42)


if __name__ == "__main__":
    unittest.main()
