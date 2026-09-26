# Ling Mapper

Preliminary dataset-independent records, PERSUADE import, and argument-graph extraction with Claude for RQ1 representation evaluation. Python 3.10+; everything uses only the standard library except extraction, which needs the `anthropic` package. Alignment, hierarchy and diagnosis are not implemented yet.

## Run the electoral-college pilot

From the project root:

```sh
PYTHONPATH=src python3 -m ling_mapper.prepare_data \
  --input data/persuade_corpus_2.0_train.csv \
  --holistic data/persuade_2.0_human_scores_demo_id_github.csv \
  --prompt 'Does the electoral college work?' \
  --pilot-size 20 --seed 42 \
  --inspected persuade:E0737CDC1E99 \
  --output-dir data/processed/electoral_college_v6
```

The current run is saved under `data/processed/electoral_college_v6/`. Earlier runs v1–v5 were deleted after v6 was confirmed; the version history below records what each changed (v5 records are byte-identical to v6). `--inspected` (repeatable) names essays examined while designing the method: any drawn for `pilot_check` moves to `development` and is replaced by the next unselected essay of the same score band in the seeded order; `splits.json` records both lists. Use a new or empty output directory; the CLI does not overwrite previous runs. Omit `--prompt` to import every essay. Omit `--pilot-size` to skip sampling. The optional holistic file is used to check matching essay text; the annotation file already includes the required essay text and prompt. A holistic-only input is supported with `gold_spans=null`.

Outputs:

- `records.jsonl`: all matching essays as common records, with recovered annotations and provenance.
- `import_report.json`: recovery methods, exclusions by role/prompt, join discrepancies, raw ID collisions, and hierarchy candidate counts.
- `pilot.jsonl`: deterministic score-band sample from the official training partition.
- `splits.json`: disjoint development/pilot-check essay IDs, seed, and RQ1 purpose.

The v5 and v6 runs contain 1,818 essays and 19,561 recovered spans out of 19,894 annotation rows. Of the 333 unresolved rows, 286 are empty/whitespace annotations, 38 are Unannotated word fragments overlapping a labelled span, 8 are ambiguous repeated text, and 1 is not found; all labelled discourse elements are recovered except one Rebuttal. 19,532 spans are confirmed at their supplied offsets; 45 were located by searching the essay. No two recovered spans overlap. All 1,818 essays join to the holistic file (4 by exact text only, after ID corruption). The v6 pilot has 21 essays: 11 development and 10 pilot-check. E0737CDC1E99 was used to design the argument-graph contract, so it moved to development and C70EE5903373 (score 3) replaced it in pilot-check. Viewers generated before v6 displayed the original pilot-check essays; the v6 viewers and Gephi files contain development essays only, and new ones should too. These are import results, not extraction model scores.

### Version history

| Run | Loader change |
|---|---|
| v1 | Offset and essay-wide text matching |
| v2 | Text-hash IDs for corrupted essay IDs, join on exact text, sequence/nearest-offset disambiguation, displacement stats |
| v3 | Reject searched matches that contradict annotation order |
| v4 | Prefer a whitespace-trimmed match within ±10 characters of the supplied offsets |
| v5 | Drop Unannotated fragments that overlap a labelled span |
| v6 | Same records as v5 (identical hash); design-inspected essay moved out of pilot-check |

## Common record boundary

`ExampleRecord` in `src/ling_mapper/schemas.py` holds prompt, unchanged response text, optional source passages, optional rubric, optional gold spans/relations, and metadata. `from_dict()` validates JSON round trips and checks every span against its source text.

Call `record.model_input()` for downstream model inputs. This allowlist omits gold annotations, effectiveness/holistic scores, demographics, hierarchy candidates, and dataset metadata. Source titles remain citation metadata and are never represented as actual passages. This import has no passage content or rubric attached.

New datasets should provide adapters returning the same record. Missing annotations are `null`; an available annotation collection with no recovered spans is `[]` plus its unresolved rows and annotation status. Check those metadata fields before interpreting an empty list as a negative example.

## Span recovery and limitations

Recovery never modifies `response_text`. It tries:

1. Exact matches at the supplied end-exclusive or inclusive boundaries.
2. A unique whitespace-trimmed match within ±10 characters of the supplied offsets (`offset_trimmed`).
3. A unique exact match anywhere in the essay.
4. A unique match after trimming annotation boundary whitespace.
5. A unique whitespace-normalised match with an index map back to original characters.

Matches from tiers 3–5 that lie outside every longest order-consistent chain of recovered spans are rejected as `sequence_conflict`. Repeated text is then resolved only if a single candidate lies between independently recovered neighbours (`sequence_unique`) or one candidate is clearly nearest the supplied offset (`nearest_clear`); otherwise it remains ambiguous. Unannotated rows overlapping a labelled span are dropped as source gap artefacts. Each recovered span records its displacement from the supplied offsets; the report gives the distribution and the 50 largest. Empty/whitespace-only annotations and missing text remain unresolved. Each recovered span preserves raw fields, original label, source-file hash, CSV record number, recovery method, and review status. Composite annotation IDs are generated from essay ID, original boundaries, and original role because raw discourse IDs repeat. Duplicate composite keys or inconsistent essay metadata fail explicitly.

`gold_spans` means source annotations with mechanically recovered positions, not human certification of every recovery. Individual spans stay marked `not_human_reviewed`. A stratified sample of 101 v4 spans was reviewed (sampled from the v4 run; sheets and confirmed verdicts are kept in `data/annotations/review_v4/`): all 89 labelled spans were correctly located and bounded; the 12 errors were Unannotated word fragments, now dropped in v5. Verdicts were proposed by Claude and confirmed by the user, not independently blind-reviewed. Report exclusions by role. Unresolved annotations are retained in `metadata.unresolved_annotations`, never fabricated or silently included in span scoring. Recovered boundaries may differ from the source annotation convention, so define the evaluation convention explicitly.

Hierarchy text/role matching produces candidate parent IDs in metadata only (11,450 unique of 11,503). Raw hierarchy IDs are not trusted as unique. A review of 30 links found an argument tree whose relation type follows the child's role (Evidence/Claim support their parent, Counterclaim attacks the Position, Rebuttal attacks the Counterclaim; 2 of 30 unclear). This role rule has not been adopted; `gold_relations` remains `null`. Effectiveness ratings remain gold provenance, not misconception labels.

The pilot is deterministic and balances available score bands approximately. It does not certify annotation quality, guarantee every role occurs, or support misconception calibration. If an essay has unresolved annotations, include that missingness in evaluation rather than treating unscorable spans as absent discourse.

## Argument graph contract

`src/ling_mapper/graph_schema.py` defines the graph that extraction must produce (`argument_graph/0.1`): proposition units that tile the essay, a single-rooted primary tree of eRST relations from a fixed GUM subset, and secondary edges only when a quoted signal licenses them. `validate_graph(graph, text)` lists every violation; `argument_edges(graph)` derives support/attack from relation class and writer stance. Rules and rationale are in section 4 of `PRELIMINARY_PIPELINE_PLAN.md`.

View graphs in this format (the essay tiled into units with signals marked, the primary tree with relation labels, and a derived support/attack view; contract violations are listed, not hidden):

```sh
PYTHONPATH=src python3 -m ling_mapper.render_graph_html \
  --graph data/annotations/argument_graphs/E0737CDC1E99.json \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --output data/processed/electoral_college_v6/viewer/argument_graph_E0737CDC1E99.html
```

`data/annotations/argument_graphs/` holds the development gold graphs for four development essays (E0737CDC1E99, C0BA22AD7F2A, 3165FA4998BC, 656C7C849144). Claude wrote them; the user reviewed all four and accepted them without changes (2026-09-25). Later edits, each confirmed by the user on 2026-09-26, are listed in each file's `provenance.change_log`: four relation labels added to the inventory, one interrupted unit split with `same-unit`, and coordinated predicates re-split to segmentation rule 2 (C0BA22AD7F2A, 656C7C849144, 3165FA4998BC). They are reviewed, not independently annotated: report them that way, and prefer an independent second annotation on a subset before treating agreement with them as validity evidence. `viewer/development_graphs.html` shows all four (pass several `--graph` files to get an essay picker).

`data/annotations/argument_graphs_pilot_check/` holds pilot-check gold graphs for four of the ten pilot-check essays: the first in split order for scores 1, 3, 4 and 6 (81E51029477E, C70EE5903373, F3B4F60CE90C, 671D0569C835). Claude wrote them on 2026-09-26, before any model had extracted these essays and after prompt v0.3 was frozen. They follow the development conventions: roles come from the PERSUADE element with the largest overlap, polarity is not annotated, and edge notes record weak reasoning and factual errors. The root is the first unit that states the writer's answer to the assignment question. In three of the four essays that unit lies in PERSUADE lead or unannotated text. The user reviewed all four and accepted them without changes (2026-09-26). Like the development gold, they are reviewed rather than independently annotated.

## Extract argument graphs with Claude

```sh
pip install anthropic   # the only non-standard-library dependency, used only here
export ANTHROPIC_API_KEY=...
PYTHONPATH=src python3 -m ling_mapper.student_graph \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --splits data/processed/electoral_college_v6/splits.json \
  --output-dir data/runs/student_graph
```

`student_graph.py` produces `argument_graph/0.1` graphs in two validated stages. **Segment:** the model returns units as exact quotes, and code locates them in the unchanged essay and checks that they tile it. **Relate:** the model returns roles, stances, the primary tree, secondary edges and signal quotes, and code locates the signals and runs `validate_graph`. Failed checks are sent back verbatim for up to `--max-attempts` attempts (default 3); a graph that never validates is logged as a failure, never repaired or saved as empty. The model receives only `model_input()` (assignment and essay text), and the system prompt is generated from `graph_schema.py`. It contains no gold graphs, but from v0.2 its rules quote short phrases from development essays as examples, so development scores are optimistic. It defaults to Claude Opus 5 (`claude-opus-5`) with adaptive thinking, effort `high`, structured JSON output, and server-side refusal fallback. It runs the development split by default and refuses pilot-check essays unless `--allow-pilot-check` is given.

The prompt version is `PROMPT_VERSION` in `student_graph.py`; the current version, `student_graph/0.3`, is frozen for the pilot-check run. Score the pilot-check essays once, with the frozen prompt:

```sh
PYTHONPATH=src python3 -m ling_mapper.student_graph \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --splits data/processed/electoral_college_v6/splits.json \
  --split pilot_check --allow-pilot-check \
  --output-dir data/runs/student_graph
```

Pilot-check essays are written to the same run folder as the development essays of that configuration, so report them separately (from `per_essay` in `metrics.json`). Score the pilot-check gold graphs with `--gold-dir data/annotations/argument_graphs_pilot_check`; the gold-graph summary then covers only those four essays, while the PERSUADE summary still covers every essay in the folder. Changing the prompt after seeing pilot-check scores makes them development data.

Each run directory is keyed by prompt version, model, effort and a hash of the prompt and schemas. It holds `system_prompt.txt`, `manifest.json` (config, records hash, per-essay status and token usage), and per essay `<id>.graph.json` plus `<id>.log.json` (every attempt's output, errors, stop reason, usage and request ID). Essays already extracted under the same configuration are skipped unless `--force` is given.

## Score extracted graphs

```sh
PYTHONPATH=src python3 -m ling_mapper.evaluate \
  --run-dir data/runs/student_graph/<run folder> \
  --records data/processed/electoral_college_v6/pilot.jsonl
```

Writes `metrics.json` into the run folder. Against the development gold graphs it reports exact unit-span and unit-boundary P/R/F1, role and stance agreement, root match, attachment accuracy (plus labelled and coarse-class accuracy), and derived support/attack P/R/F1. Against PERSUADE, for every essay, it reports role agreement, Feedback-Prize-style element F1 (overlap at least half of both spans), and attachment of elements with a unique hierarchy parent. Overlaps count non-whitespace characters. A gold unit's predicted attachment is the edge leaving the predicted units mapped to it, so finer or coarser segmentation alone is not counted as an attachment error. The summary covers every essay in the run folder. Running the scorer again overwrites `metrics.json`.

### Development results

Claude Opus 5, effort `high`, one run per prompt version on the 11 development essays (4 with gold graphs). Every version extracted all 11 essays. v0.1 is scored against the gold graphs as re-split for v0.2, so all three rows use the same gold.

| Prompt | Exact unit F1 | Boundary F1 | Root | Attachment | Labelled | Role | Stance | Derived F1 | PERSUADE role | PERSUADE element F1 | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.1 | 0.79 | 0.92 | 2/4 | 0.66 | 0.53 | 0.54 | 0.85 | 0.48 | 0.62 | 0.49 | $4.19 |
| 0.2 | 0.78 | 0.91 | 3/4 | 0.72 | 0.63 | 0.79 | 0.91 | 0.59 | 0.76 | 0.62 | $4.04 |
| 0.3 | 0.79 | 0.91 | 3/4 | 0.80 | 0.72 | 0.71 | 0.97 | 0.80 | 0.73 | 0.59 | $4.66 |

v0.2 added PERSUADE-style role rules, label tests for justify versus cause and for joint-list, and splitting of predicates that share a subject. v0.3 revised only the claim and counterclaim rules. The claim/evidence boundary remains the main role error, and it moved between versions rather than shrinking. v0.1 labelled too much as claim, v0.2 too much as evidence, and v0.3 too much as claim again. Roles do not enter derived support/attack edges, which come from relations and stance, so v0.3 was frozen for its structure scores. These numbers come from essays used to tune the prompt, against gold that Claude wrote and the user reviewed. Each is a single run with no measure of run-to-run variance.

## Read essays with their argument tree

```sh
PYTHONPATH=src python3 -m ling_mapper.render_html \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --essay <development example_id> ... \
  --output data/processed/electoral_college_v6/viewer/development_viewer.html
```

A self-contained HTML page: the essay with spans highlighted by role beside its argument graph, built from hierarchy candidate links. The Graph tab draws spans as nodes with arrows child → parent (left-to-right or top-down; scroll to zoom, drag to pan); the Outline tab shows the same tree as nested cards. Hovering either side highlights its counterpart; clicking jumps to it. Arrow keys switch essays. Accepts the same `--essay` and `--include-unannotated` options as the Gephi export.

## Visualise in Gephi

```sh
PYTHONPATH=src python3 -m ling_mapper.export_gephi \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --essay <development example_id> ... \
  --output data/processed/electoral_college_v6/gephi/development_argument_graph.gexf
```

Add `--essay <example_id>` (repeatable) for specific essays and `--include-unannotated` to keep Unannotated spans. Nodes are gold spans coloured by role (Okabe-Ito palette), labelled `ROLE: text…`, and carry `role`, `essay`, full `text`, `start`, `order`, and `holistic_score`. Edges run child → candidate parent from `hierarchy_candidates` and are marked `unverified_candidate`. Each essay is pre-laid out as a tree (roots on top, children below in essay order; essays side by side), so do not run a Gephi layout, which would discard it. Open the file, choose Directed, centre the view, and turn on node labels; read full text in Data Laboratory.

## Test

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Tests cover inclusive endpoints, ambiguity, Unicode/whitespace index mapping, invalid spans, repeated raw IDs, missing supplementary joins, unavailable annotations, hierarchy candidates, model-input leakage, a second dataset-shaped fixture, deterministic essay-level splitting, offset-window recovery, order-conflict rejection, and Unannotated overlap removal. Graph tests cover contract validation, derived support/attack edges, extraction with a stubbed model (quote location, retries, failures, pilot-check refusal), and the scorer.
