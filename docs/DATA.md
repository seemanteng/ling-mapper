# Data: PERSUADE import, span recovery and gold graphs

## Build the electoral-college pilot

From the project root:

```sh
PYTHONPATH=src python3 -m argument_graph.prepare_data \
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

The v5 and v6 runs contain 1,818 essays and 19,561 recovered spans out of 19,894 annotation rows. Of the 333 unresolved rows, 286 are empty/whitespace annotations, 38 are Unannotated word fragments overlapping a labelled span, 8 are ambiguous repeated text, and 1 is not found; all labelled discourse elements are recovered except one Rebuttal. 19,532 spans are confirmed at their supplied offsets; 45 were located by searching the essay. No two recovered spans overlap. All 1,818 essays join to the holistic file (4 by exact text only, after ID corruption). The v6 pilot has 21 essays: 11 development and 10 pilot-check. E0737CDC1E99 was used to design the argument-graph contract, so it moved to development and C70EE5903373 (score 3) replaced it in pilot-check. Viewers generated before v6 displayed the original pilot-check essays; the v6 viewers contain development essays only, and new ones should too. These are import results, not extraction model scores.

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

`ExampleRecord` in `src/argument_graph/schemas.py` holds prompt, unchanged response text, optional source passages, optional rubric, optional gold spans/relations, and metadata. `from_dict()` validates JSON round trips and checks every span against its source text.

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

## Gold argument graphs

`data/annotations/argument_graphs/` holds the development gold graphs for four development essays (E0737CDC1E99, C0BA22AD7F2A, 3165FA4998BC, 656C7C849144). Claude wrote them; the user reviewed all four and accepted them without changes (2026-09-25). Later edits, each confirmed by the user on 2026-09-26, are listed in each file's `provenance.change_log`: four relation labels added to the inventory, one interrupted unit split with `same-unit`, and coordinated predicates re-split to segmentation rule 2 (C0BA22AD7F2A, 656C7C849144, 3165FA4998BC). They are reviewed, not independently annotated: report them that way, and prefer an independent second annotation on a subset before treating agreement with them as validity evidence. `viewer/development_graphs.html` shows all four (pass several `--graph` files to get an essay picker).

`data/annotations/argument_graphs_pilot_check/` holds pilot-check gold graphs for four of the ten pilot-check essays: the first in split order for scores 1, 3, 4 and 6 (81E51029477E, C70EE5903373, F3B4F60CE90C, 671D0569C835). Claude wrote them on 2026-09-26, before any model had extracted these essays and after prompt v0.3 was frozen. They follow the development conventions: roles come from the PERSUADE element with the largest overlap, polarity is not annotated, and edge notes record weak reasoning and factual errors. The root is the first unit that states the writer's answer to the assignment question. In three of the four essays that unit lies in PERSUADE lead or unannotated text. The user reviewed all four and accepted them without changes (2026-09-26). Like the development gold, they are reviewed rather than independently annotated.

Later edits to both gold sets (the conceded-passage convention of prompt v0.4, 2026-09-27, and one corrected note) are logged in each file's `provenance.change_log`, with `confirmed_by: null` until reviewed.

## Read essays with their PERSUADE argument tree

```sh
PYTHONPATH=src python3 -m argument_graph.render_html \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --essay <development example_id> ... \
  --output data/processed/electoral_college_v6/viewer/development_viewer.html
```

A self-contained HTML page: the essay with spans highlighted by role beside its argument graph, built from hierarchy candidate links. The Graph tab draws spans as nodes with arrows child → parent (left-to-right or top-down; scroll to zoom, drag to pan); the Outline tab shows the same tree as nested cards. Hovering either side highlights its counterpart; clicking jumps to it. Arrow keys switch essays. Add `--essay <example_id>` (repeatable) for specific essays and `--include-unannotated` to keep Unannotated spans.

## GUM: expert eRST reference

GUM (Georgetown University Multilayer corpus) is annotated in eRST, the scheme the graph contract adapts, so its trees serve as an expert-annotated check on relation labelling. `argument_graph.loaders.gum` converts GUM documents into records and gold graphs. The dependency files use the same head-ordered conversion as this project (satellite to nucleus, multinuclear members chained to the first), so the gold tree is GUM's own; only character offsets are added. The text is rebuilt from the CoNLL-U sentence strings, and every EDU token must be found in order or the import fails.

```sh
git clone --depth 1 --filter=blob:none --sparse https://github.com/amir-zeldes/gum.git <gum dir>
git -C <gum dir> sparse-checkout set rst/dependencies dep
PYTHONPATH=src python3 -m argument_graph.loaders.gum --gum-dir <gum dir> --output-dir data/processed/gum_v1
PYTHONPATH=src python3 -m argument_graph.student_graph --records data/processed/gum_v1/records.jsonl \
  --splits data/processed/gum_v1/splits.json --split gum --output-dir data/runs/gum
PYTHONPATH=src python3 -m argument_graph.evaluate --run-dir data/runs/gum/<run folder> \
  --records data/processed/gum_v1/records.jsonl --gold-dir data/processed/gum_v1/gold
```

The default documents are the essay and letter documents of GUM's standard test partition: `GUM_essay_fear`, `GUM_essay_system`, `GUM_letter_attorney` and `GUM_letter_mandela` (821–1,070 words, 525 EDUs, 521 primary edges). They were not used to design prompts. Limits: gold graphs keep GUM's 32-label inventory, and only 367 of the 521 primary edges carry a label the contract allows, so exact-label accuracy cannot exceed 0.70 (`labelled_accuracy_in_inventory` scores the rest); GUM EDUs follow GUM's segmentation guidelines, which are finer than this project's in places; GUM has no roles or stances, so those scores and derived support/attack are not computed; signals and secondary edges are imported but not scored. The texts are published writing, not student essays, and the record prompt states that no assignment question exists. Texts are CC BY / BY-NC-SA and annotations CC BY 4.0 (see GUM's LICENSE.md); the built files stay under the gitignored `data/processed/`.
