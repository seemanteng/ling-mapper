import os
import tempfile
import unittest
from pathlib import Path

from argument_graph.providers import load_env, parse_json


class ProviderHelpersTest(unittest.TestCase):
    def test_load_env_reads_pairs_and_keeps_existing_variables(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('# comment\nPROV_TEST_A=abc\nexport PROV_TEST_B="two words"\n\nPROV_TEST_C = x=y\nPROV_TEST_KEPT=new\n')
            os.environ["PROV_TEST_KEPT"] = "old"
            try:
                load_env(path)
                self.assertEqual(os.environ["PROV_TEST_A"], "abc")
                self.assertEqual(os.environ["PROV_TEST_B"], "two words")
                self.assertEqual(os.environ["PROV_TEST_C"], "x=y")
                self.assertEqual(os.environ["PROV_TEST_KEPT"], "old")
            finally:
                for k in ("PROV_TEST_A", "PROV_TEST_B", "PROV_TEST_C", "PROV_TEST_KEPT"):
                    os.environ.pop(k, None)

    def test_load_env_ignores_a_missing_file(self):
        load_env("/nonexistent/.env")

    def test_parse_json(self):
        self.assertEqual(parse_json('{"a": 1}'), ({"a": 1}, None))
        self.assertEqual(parse_json('<think>hmm {x}</think>\n{"a": 1}'), ({"a": 1}, None))
        self.assertIsNone(parse_json('{"a": ')[0])
        self.assertIn("invalid_json", parse_json('{"a": ')[1])
        self.assertEqual(parse_json("")[0], None)


if __name__ == "__main__":
    unittest.main()


class BackoffTest(unittest.TestCase):
    def test_transient_errors_are_retried_then_succeed(self):
        from argument_graph.providers import with_backoff

        class Busy(Exception):
            status_code = 429

        calls, waits = [], []
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise Busy("high traffic")
            return "ok"
        self.assertEqual(with_backoff(flaky, sleep=waits.append), "ok")
        self.assertEqual(waits, [5.0, 10.0])

    def test_quota_credit_and_client_errors_are_not_retried(self):
        from argument_graph.providers import with_backoff

        class Err(Exception):
            def __init__(self, status, msg):
                super().__init__(msg)
                self.status_code = status
        for status, msg in ((429, "You exceeded your current quota"), (402, "no remaining credits"), (400, "bad request")):
            calls = []
            def fail():
                calls.append(1)
                raise Err(status, msg)
            with self.assertRaises(Err):
                with_backoff(fail, sleep=lambda s: None)
            self.assertEqual(len(calls), 1)

    def test_gives_up_after_the_last_try(self):
        from argument_graph.providers import with_backoff

        class Busy(Exception):
            status_code = 503
        calls = []
        def always():
            calls.append(1)
            raise Busy("down")
        with self.assertRaises(Busy):
            with_backoff(always, tries=3, sleep=lambda s: None)
        self.assertEqual(len(calls), 3)
