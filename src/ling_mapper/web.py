"""Local web page: paste an assignment and an essay, get its argument graph.

Runs the same two-stage extraction as `student_graph.py` (current prompt, validation and
retries) and shows the result in the `render_graph_html` viewer. Serves on 127.0.0.1 only.
Every request is saved under --output-dir (inputs, graph or failure, and the full attempt
log), so a graph shown here can be traced like one from a batch run.
"""
import argparse
import hashlib
import json
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .render_graph_html import render
from .schemas import ExampleRecord
from .student_graph import DEFAULT_MODEL, PROMPT_VERSION, AnthropicCaller, config_hash, extract

MAX_CHARS = 20000
# Claude Opus 5 list prices per token, used only for the cost estimate shown on the page.
PRICES = {"claude-opus-5": (5e-6, 25e-6)}


def run_extraction(prompt, essay, caller, model, effort, output_dir, max_attempts=3):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha256((prompt + "\n" + essay).encode()).hexdigest()[:8]
    record = ExampleRecord(example_id=f"web:{stamp}-{digest}", prompt=prompt, response_text=essay)
    attempts = []
    try:
        result = extract(record, caller(), max_attempts, attempts)
    except Exception as exc:  # an API or credential error is reported on the page, not swallowed
        attempts.append({"stage": "error", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        result = {"graph": None, "failed_stage": "error", "attempts": attempts}
    usage = [a.get("usage", {}) for a in attempts]
    tokens = {"input": sum(u.get("input_tokens", 0) for u in usage), "output": sum(u.get("output_tokens", 0) for u in usage)}
    price = PRICES.get(model)
    cost = round(tokens["input"] * price[0] + tokens["output"] * price[1], 2) if price else None
    run_dir = output_dir / f"{stamp}-{digest}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.json").write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
    (run_dir / "log.json").write_text(json.dumps(attempts, indent=2, ensure_ascii=False, default=str))
    summary = {"prompt_version": PROMPT_VERSION, "config_hash": config_hash(model, effort), "model": model,
               "effort": effort, "attempts": len(attempts), "tokens": tokens, "cost_usd": cost, "saved_to": str(run_dir)}
    graph = result["graph"]
    if graph is None:
        last = next((a for a in reversed(attempts) if a.get("errors") or a.get("error")), {})
        summary.update(ok=False, failed_stage=result["failed_stage"],
                       errors=last.get("errors") or [last.get("error", "no output")])
    else:
        graph["provenance"] = {"annotator": f"{model} ({PROMPT_VERSION}, effort {effort})",
                               "review_status": "not_human_reviewed", "config_hash": summary["config_hash"]}
        (run_dir / "graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False))
        summary.update(ok=True, html=render([(graph, record.to_dict())], "Argument graph"))
    (run_dir / "summary.json").write_text(json.dumps({k: v for k, v in summary.items() if k != "html"}, indent=2))
    return summary


class Handler(BaseHTTPRequestHandler):
    model, effort, output_dir = DEFAULT_MODEL, "high", Path("data/runs/web")

    def _send(self, code, body, kind):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/":
            return self._send(404, "Not found", "text/plain")
        page = PAGE.replace("__MODEL__", self.model).replace("__EFFORT__", self.effort).replace("__VERSION__", PROMPT_VERSION)
        self._send(200, page, "text/html")

    def do_POST(self):
        if self.path != "/extract":
            return self._send(404, "Not found", "text/plain")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            prompt, essay = body.get("prompt", "").strip(), body.get("essay", "")
        except (ValueError, AttributeError):
            return self._send(400, json.dumps({"ok": False, "errors": ["Request was not valid JSON."]}), "application/json")
        problems = [m for m, bad in (("Enter the essay question.", not prompt), ("Enter the essay.", not essay.strip()),
                                     (f"The essay is longer than {MAX_CHARS} characters.", len(essay) > MAX_CHARS)) if bad]
        if problems:
            return self._send(400, json.dumps({"ok": False, "errors": problems}), "application/json")
        summary = run_extraction(prompt, essay, lambda: AnthropicCaller(self.model, self.effort),
                                 self.model, self.effort, self.output_dir)
        self._send(200, json.dumps(summary, ensure_ascii=False), "application/json")

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Essay Argument Graph</title>
<style>
:root { --bg: #fafaf8; --panel: #ffffff; --ink: #1d1d1f; --muted: #6b6b70; --line: #e3e3e0; --warn: #b3261e;
        --accent: #0072b2; color-scheme: light; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161618; --panel: #1f1f22; --ink: #ececef; --muted: #9a9aa2; --line: #333338; --warn: #ff8a80;
          --accent: #56b4e9; color-scheme: dark; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { border-bottom: 1px solid var(--line); padding: 10px 20px; display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: baseline; }
header h1 { font-size: 16px; margin: 0; font-weight: 600; }
.meta { color: var(--muted); font-size: 13px; }
form { max-width: 860px; margin: 24px auto; padding: 0 16px; display: grid; gap: 16px; }
label { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 600; }
textarea { width: 100%; font: inherit; color: inherit; background: var(--panel); border: 1px solid var(--line);
           border-radius: 8px; padding: 10px 12px; resize: vertical; }
textarea:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
#prompt { min-height: 80px; }
#essay { min-height: 320px; }
.row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
button { font: inherit; font-size: 14px; border-radius: 8px; padding: 8px 16px; cursor: pointer;
         background: var(--ink); color: var(--panel); border: 1px solid var(--ink); }
button:disabled { opacity: .5; cursor: progress; }
button.plain { background: var(--panel); color: var(--ink); border-color: var(--line); font-size: 13px; padding: 4px 10px; }
#status { color: var(--muted); font-size: 13px; }
#errors { color: var(--warn); font-size: 14px; margin: 0; padding-left: 18px; }
#result { display: none; }
#result .bar { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; padding: 8px 20px; border-bottom: 1px solid var(--line); }
#frame { width: 100%; height: calc(100vh - 96px); border: 0; display: block; }
</style>
</head>
<body>
<header>
  <h1>Essay argument graph</h1>
  <span class="meta">__MODEL__ · effort __EFFORT__ · prompt __VERSION__</span>
</header>
<form id="form">
  <div><label for="prompt">Essay question</label>
    <textarea id="prompt" required placeholder="The assignment the student answered"></textarea></div>
  <div><label for="essay">Essay</label>
    <textarea id="essay" required placeholder="Paste the student's essay exactly as written"></textarea></div>
  <div class="row">
    <button id="go" type="submit">Generate graph</button>
    <span id="status">Takes one to four minutes; each essay costs roughly $0.30 to $1.</span>
  </div>
  <ul id="errors"></ul>
</form>
<div id="result">
  <div class="bar">
    <button class="plain" id="back" type="button">&larr; Edit or new essay</button>
    <span class="meta" id="info"></span>
  </div>
  <iframe id="frame" title="Argument graph"></iframe>
</div>
<script>
const $ = id => document.getElementById(id);
const store = { get(k) { try { return sessionStorage.getItem(k) || ""; } catch { return ""; } },
                set(k, v) { try { sessionStorage.setItem(k, v); } catch {} } };
["prompt", "essay"].forEach(k => { $(k).value = store.get(k); $(k).oninput = () => store.set(k, $(k).value); });
function showErrors(list) { $("errors").replaceChildren(...list.map(e => Object.assign(document.createElement("li"), {textContent: e}))); }
$("back").onclick = () => { $("result").style.display = "none"; $("form").style.display = ""; document.querySelector("header").style.display = ""; };
$("form").onsubmit = async ev => {
  ev.preventDefault();
  showErrors([]);
  $("go").disabled = true;
  const started = Date.now();
  const tick = setInterval(() => $("status").textContent = `Working… ${Math.round((Date.now() - started) / 1000)} s (segmenting, then building the graph)`, 1000);
  try {
    const res = await fetch("/extract", { method: "POST", headers: {"Content-Type": "application/json"},
                                          body: JSON.stringify({prompt: $("prompt").value, essay: $("essay").value}) });
    const out = await res.json();
    const cost = out.cost_usd != null ? ` · about $${out.cost_usd.toFixed(2)}` : "";
    if (out.ok) {
      $("info").textContent = `${out.attempts} model calls · ${out.tokens.input.toLocaleString()} in / ${out.tokens.output.toLocaleString()} out tokens${cost} · saved to ${out.saved_to}`;
      $("frame").srcdoc = out.html;
      $("form").style.display = "none"; document.querySelector("header").style.display = "none";
      $("result").style.display = "block";
      $("status").textContent = "Done.";
    } else {
      const where = out.failed_stage ? `Extraction failed at the ${out.failed_stage} stage${cost}. Last errors:` : "Please fix:";
      showErrors([where, ...(out.errors || [])]);
      $("status").textContent = out.saved_to ? `Log saved to ${out.saved_to}` : "";
    }
  } catch (e) {
    showErrors([`Could not reach the local server: ${e}`]);
    $("status").textContent = "";
  } finally {
    clearInterval(tick);
    $("go").disabled = false;
  }
};
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--output-dir", type=Path, default=Path("data/runs/web"))
    args = parser.parse_args()
    Handler.model, Handler.effort, Handler.output_dir = args.model, args.effort, args.output_dir
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Open http://127.0.0.1:{args.port}  (model {args.model}, effort {args.effort}, prompt {PROMPT_VERSION}; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
