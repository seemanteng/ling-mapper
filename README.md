# Ling Mapper

Turn a student's argumentative essay into a validated argument graph. Given the assignment question and the student's response, Claude segments the essay into clause-level units and links them with discourse relations. The result is checked against a strict contract and shown in a browser viewer.

Python 3.10+. Everything uses only the standard library except extraction, which needs the `anthropic` package. The code is in `src/argument_graph/`.

## Scope

The deliverable is **student graph extraction** from a question and a response. Misconception detection is out of scope until a workable approach is found. Source alignment and findings were prototyped and are kept as exploratory work (see [docs/EXPLORATORY.md](docs/EXPLORATORY.md)).

## Quick start

```sh
pip install anthropic
export ANTHROPIC_API_KEY=...
PYTHONPATH=src python3 -m argument_graph.web        # then open http://127.0.0.1:8000
```

Paste the essay question and the essay, then click **Generate graph**. An essay takes one to four minutes and costs roughly $0.30 to $1 (Claude Opus 5, effort `high`). The page listens on 127.0.0.1 only; `--port`, `--model`, `--effort` and `--output-dir` change the defaults. Every request is saved under `data/runs/web/<time>-<hash>/` (gitignored): `input.json`, `log.json` (every attempt), `summary.json` (tokens, estimated cost, configuration) and `graph.json` when extraction succeeds. A failed extraction shows the stage and the checks that failed, never a partial graph.

## What a graph contains

The contract is `argument_graph/0.1`, defined in `src/argument_graph/graph_schema.py`. The rules and their rationale are in section 4 of [PRELIMINARY_PIPELINE_PLAN.md](PRELIMINARY_PIPELINE_PLAN.md).

- **Units** are exact quotes that together cover every character of the essay. Each unit has a **role** (lead, position, claim, counterclaim, rebuttal, evidence, concluding summary, unannotated), a **stance** (whether the writer puts it forward as their own view: endorsed, conceded, rejected, reported, unclear) and a **polarity** (negative only when the main claim is negated).
- **Relations** come from a fixed set of eRST/GUM labels, such as explanation-justify, adversative-concession and elaboration-additional. They form a single-rooted primary tree, rooted at the thesis. A secondary relation is allowed only when a quoted signal in the essay licenses it. Every relation quotes the words that signal it, or is marked implicit.
- **Support and attack** are derived from relations and stance (`argument_edges`), not labelled separately.
- **Propositions** (`propositions`) join each unit with its reporting frame, its conditions and its split-off parts ("Critics may argue" + "that technology leads to social good…"). This view is derived; the graph itself is unchanged.

`validate_graph(graph, text)` lists every violation of the contract and never repairs a graph.

## How extraction works

`src/argument_graph/student_graph.py` works in two stages, and each is validated in code.
1. **Segment:** the model returns units as exact quotes, and code locates them in the unchanged essay. If a quote has no exact match, whitespace is matched loosely, and the stored text is always the essay's own slice.
2. **Relate:** the model returns roles, stances, the tree and signal quotes, and `validate_graph` checks the result.

Failed checks go back to the model, up to 3 attempts. A graph that never validates is logged as a failure, never repaired. The model sees only the assignment and essay text. The current prompt is `student_graph/0.4`.

To extract a batch of PERSUADE essays (see [docs/DATA.md](docs/DATA.md) for building the records):

```sh
PYTHONPATH=src python3 -m argument_graph.student_graph \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --splits data/processed/electoral_college_v6/splits.json \
  --output-dir data/runs/student_graph                  # --split pilot_check --allow-pilot-check for the other split
```

Each run folder is keyed by prompt version, model, effort and a hash of the prompt and schemas. It holds `system_prompt.txt` and `manifest.json` (status and token usage per essay), and for each essay `<id>.graph.json` and `<id>.log.json`. Essays already extracted under the same configuration are skipped unless `--force` is given.

## View and score graphs

```sh
PYTHONPATH=src python3 -m argument_graph.render_graph_html --graph <graph.json> [--graph ...] \
  --records <records.jsonl> --output viewer.html

PYTHONPATH=src python3 -m argument_graph.evaluate --run-dir data/runs/student_graph/<run folder> \
  --records data/processed/electoral_college_v6/pilot.jsonl [--gold-dir data/annotations/argument_graphs_pilot_check]
```

The viewer shows the essay tiled into units next to three views: **Relations** (the tree), **Support / attack** and **Propositions**. Contract violations are listed, not hidden.

The scorer writes `metrics.json` into the run folder, overwriting any earlier one. Against gold graphs it reports unit segmentation, root match, attachment (plain and labelled), role and stance agreement, and derived support/attack F1. Against PERSUADE it reports role agreement and element F1. Four GUM documents with expert eRST trees give a check on relation labelling that does not depend on the Claude-written gold graphs (see [docs/DATA.md](docs/DATA.md#gum-expert-erst-reference)).

## Current quality

Prompt `student_graph/0.4`, one run each (2026-09-27), against 4 gold graphs per set.

| | Exact unit F1 | Root | Attachment | Labelled | Stance | Support/attack F1 | PERSUADE role |
|---|---|---|---|---|---|---|---|
| Development essays | 0.81 | 3/4 | 0.80 | 0.66 | 0.97 | 0.73 | 0.73 |
| Pilot-check essays | 0.91 | 3/4 | 0.72 | 0.67 | 0.94 | 0.66 | 0.69 |

Read these with care:
- **The gold graphs are small and not independent.** There are 4 per set, written by Claude and reviewed by the user, not annotated independently.
- **Neither set is untouched.** The development essays shaped the prompt, and the pilot-check essays have been scored twice.
- **Small differences are noise.** One run on 4 essays moves by about 0.05 from run to run.
- **Roles are the weakest part.** The claim/evidence boundary is the main error.

The full history of prompt versions v0.1–v0.4 is in [docs/EXTRACTION_RESULTS.md](docs/EXTRACTION_RESULTS.md).

## Data and gold graphs

- **The PERSUADE 2.0 electoral-college prompt:** 1,818 essays, imported with recovered discourse spans. The pilot has 21 essays: 11 for development and 10 for pilot-check. See [docs/DATA.md](docs/DATA.md).
- **Gold graphs:** `data/annotations/argument_graphs/` holds 4 development essays and `data/annotations/argument_graphs_pilot_check/` holds 4 pilot-check essays. Changes are logged in each file's `provenance.change_log`.
- **Large inputs and every run** (`data/processed/`, `data/runs/`) are gitignored. So are the copyrighted source passages (`data/sources/`).

## Repository layout

| Module | Purpose |
|---|---|
| `student_graph.py` | Extraction (two validated stages), prompt and CLI |
| `graph_schema.py` | Graph contract, `validate_graph`, `argument_edges`, `propositions` |
| `web.py` | Local browser page for single essays |
| `render_graph_html.py` | Graph viewer |
| `evaluate.py` | Scoring against gold graphs and PERSUADE |
| `schemas.py`, `loaders/persuade.py`, `prepare_data.py`, `spans.py`, `review_sample.py`, `render_html.py` | Dataset records, PERSUADE import, span recovery, the review sample, the PERSUADE tree viewer |
| `fetch_sources.py`, `source_graph.py`, `render_source_html.py`, `align.py`, `findings.py`, `render_findings_html.py` | Exploratory: source passages, reference graph, alignment and findings |

## Open questions

- **The root rule.** Should the root be the first statement of the writer's answer (as in the gold) or PERSUADE's position unit? It causes the one root miss per set.
- **Cost.** Effort `medium` or Sonnet 5 may cut the cost per essay; this is untested.
- **A single-essay command-line tool.** At present the browser page is the only way to extract an essay outside PERSUADE records.

## Test

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

Tests cover the contract and its validator, extraction with a scripted model (quote location, retries, failures, pilot-check refusal), the scorer, the viewers, the browser page and the PERSUADE import. The exploratory modules have their own tests.
