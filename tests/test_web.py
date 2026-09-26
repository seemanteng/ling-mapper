import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from argument_graph.web import Handler, run_extraction
from test_student_graph import QUOTES, RELATE, TEXT, ScriptedCaller


class RunExtractionTests(unittest.TestCase):
    def test_success_renders_viewer_and_saves_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_extraction("Argue for or against.", TEXT, lambda: ScriptedCaller({"units": QUOTES}, RELATE),
                                 "claude-opus-5", "high", Path(d))
            self.assertTrue(out["ok"])
            self.assertIn("<html", out["html"])
            self.assertEqual(out["tokens"], {"input": 20, "output": 10})
            saved = Path(out["saved_to"])
            self.assertEqual(sorted(p.name for p in saved.iterdir()), ["graph.json", "input.json", "log.json", "summary.json"])
            self.assertEqual(json.loads((saved / "graph.json").read_text())["root"], "u1")

    def test_failure_reports_stage_and_errors_without_a_graph(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_extraction("Q", TEXT, lambda: ScriptedCaller({"units": ["not in the essay"]}),
                                 "claude-opus-5", "high", Path(d), max_attempts=1)
            self.assertFalse(out["ok"])
            self.assertEqual(out["failed_stage"], "segment")
            self.assertTrue(any("not an exact quote" in e for e in out["errors"]))
            self.assertFalse((Path(out["saved_to"]) / "graph.json").exists())

    def test_caller_exception_is_reported(self):
        def broken():
            raise RuntimeError("no API key")
        with tempfile.TemporaryDirectory() as d:
            out = run_extraction("Q", TEXT, broken, "claude-opus-5", "high", Path(d))
            self.assertFalse(out["ok"])
            self.assertIn("no API key", out["errors"][0])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_form_page_is_served(self):
        page = urllib.request.urlopen(self.url + "/").read().decode()
        self.assertIn("Essay question", page)

    def test_missing_inputs_are_rejected_before_any_model_call(self):
        req = urllib.request.Request(self.url + "/extract", data=json.dumps({"prompt": "", "essay": " "}).encode(),
                                     headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(json.loads(ctx.exception.read())["errors"], ["Enter the essay question.", "Enter the essay."])


if __name__ == "__main__":
    unittest.main()
