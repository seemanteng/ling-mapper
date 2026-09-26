# Ling Mapper

Preliminary dataset-independent records, PERSUADE import, and argument-graph extraction with Claude for RQ1 representation evaluation. Python 3.10+; everything uses only the standard library except extraction, which needs the `anthropic` package. Alignment, hierarchy and diagnosis are not implemented yet.

## Status (2026-09-26)

Code lives in the `argument_graph` package (`src/argument_graph/`, renamed from `ling_mapper`). Details and numbers are in the sections below and in `PRELIMINARY_PIPELINE_PLAN.md`.

| Stage | State |
|---|---|
| PERSUADE import (Phase A) | Done: electoral-college run v6, 21-essay pilot (11 development, 10 pilot-check). |
| Student graph extraction (Phase B) | Prompt `student_graph/0.3` frozen. Scored on development and, once, on pilot-check essays. The pilot-check essays are now used, so a changed prompt needs a new held-out sample. |
| Gold graphs | 4 development and 4 pilot-check essays: Claude-written, user-reviewed, not independently annotated. |
| Source passages | Obtained (`fetch_sources`); second-hand copy, not yet compared with Kaggle's original. Gitignored (copyright). |
| Reference graph (Phase B step 1) | Drafted as source graphs (a format for passages, not essays) for all three sources, plus the assignment's explicit expectations. Awaiting review. |
| Browser page | `argument_graph.web`: paste a question and an essay to get its graph. |
| Alignment (Phase C) | Prototype built (`argument_graph.align`): a model judge links each student unit to the source units it draws on, with gold alignments for the 8 gold essays and a word-overlap baseline. Judge `align/0.2` (with rules R1–R3) on 6 held-out essays: label accuracy 0.83, source-use F1 0.91, link F1 0.67, 10 of 13 distortions found (7 flagged that the gold reads charitably). The development essays score about the same. |
| Findings (Phase C) | First version (`argument_graph.findings`, rules only): possible misconceptions from distorted alignments, unsupported claims, and unmet assignment requirements, each marked for review, with a review page. Feedback wording not started. |
| Concept grouping (Phase D) | Not started. Within one essay, a model groups verified units by topic. Across essays and the reference graph, embedding clustering supplies alignment candidates. |

Decisions taken on 2026-09-26:
- Predicates that share a subject are split into separate units.
- A fact the writer cites from a source and uses as their own evidence is `endorsed`; the next prompt version must say so.
- The graph viewer is kept; the Gephi export was removed.

Still open:
- The root rule: the first statement of the writer's answer (used in the gold) or PERSUADE's position unit.
- Adding a separate verification pass (Phase B step 4).

## Run the electoral-college pilot

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

## Argument graph contract

`src/argument_graph/graph_schema.py` defines the graph that extraction must produce (`argument_graph/0.1`): proposition units that tile the essay, a single-rooted primary tree of eRST relations from a fixed GUM subset, and secondary edges only when a quoted signal licenses them. `validate_graph(graph, text)` lists every violation; `argument_edges(graph)` derives support/attack from relation class and writer stance. Rules and rationale are in section 4 of `PRELIMINARY_PIPELINE_PLAN.md`.

View graphs in this format (the essay tiled into units with signals marked, the primary tree with relation labels, and a derived support/attack view; contract violations are listed, not hidden):

```sh
PYTHONPATH=src python3 -m argument_graph.render_graph_html \
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
PYTHONPATH=src python3 -m argument_graph.student_graph \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --splits data/processed/electoral_college_v6/splits.json \
  --output-dir data/runs/student_graph
```

`student_graph.py` produces `argument_graph/0.1` graphs in two validated stages. **Segment:** the model returns units as exact quotes, and code locates them in the unchanged essay and checks that they tile it. **Relate:** the model returns roles, stances, the primary tree, secondary edges and signal quotes, and code locates the signals and runs `validate_graph`. A quote is located exactly if possible; failing that, a whitespace run in the quote may match any whitespace run in the essay, because the model cannot reproduce characters such as non-breaking spaces. The stored unit or signal is always the essay's own slice. This fallback was added after two pilot-check essays failed on `\xa0` (2026-09-26); it leaves every earlier successful segmentation unchanged. Failed checks are sent back verbatim for up to `--max-attempts` attempts (default 3); a graph that never validates is logged as a failure, never repaired or saved as empty. The model receives only `model_input()` (assignment and essay text), and the system prompt is generated from `graph_schema.py`. It contains no gold graphs, but from v0.2 its rules quote short phrases from development essays as examples, so development scores are optimistic. It defaults to Claude Opus 5 (`claude-opus-5`) with adaptive thinking, effort `high`, structured JSON output, and server-side refusal fallback. It runs the development split by default and refuses pilot-check essays unless `--allow-pilot-check` is given.

The prompt version is `PROMPT_VERSION` in `student_graph.py`; the current version, `student_graph/0.3`, is frozen for the pilot-check run. Score the pilot-check essays once, with the frozen prompt:

```sh
PYTHONPATH=src python3 -m argument_graph.student_graph \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --splits data/processed/electoral_college_v6/splits.json \
  --split pilot_check --allow-pilot-check \
  --output-dir data/runs/student_graph
```

Pilot-check essays are written to the same run folder as the development essays of that configuration, so report them separately (from `per_essay` in `metrics.json`). Score the pilot-check gold graphs with `--gold-dir data/annotations/argument_graphs_pilot_check`; the gold-graph summary then covers only those four essays, while the PERSUADE summary still covers every essay in the folder. Changing the prompt after seeing pilot-check scores makes them development data.

Each run directory is keyed by prompt version, model, effort and a hash of the prompt and schemas. It holds `system_prompt.txt`, `manifest.json` (config, records hash, per-essay status and token usage), and per essay `<id>.graph.json` plus `<id>.log.json` (every attempt's output, errors, stop reason, usage and request ID). Essays already extracted under the same configuration are skipped unless `--force` is given.

## Source passages and reference graph

The electoral-college assignment asks students to argue from three sources, but PERSUADE records carry only their titles. The passages, with the paragraph numbers students cite, come from the Kaggle "LLM - Detect AI Generated Text" competition (`train_prompts.csv`), run by the same organisers as PERSUADE. The script downloads a public copy pinned to a commit, checks its SHA-256, and decodes it (the copy is GBK-encoded):

```sh
PYTHONPATH=src python3 -m argument_graph.fetch_sources            # or --csv <downloaded file>
```

It writes `data/sources/electoral_college/`: `source_text.md`, `instructions.txt`, `paragraphs.json`, `source_records.jsonl` (one record per source, paragraph numbers as offsets) and `provenance.json`. The copy has not yet been compared with Kaggle's original, which needs a login. Its paragraph numbers match student citations ("paragraph 12"), and every factual note in the pilot-check gold agrees with it. If your Python cannot verify HTTPS certificates (python.org installs on macOS until "Install Certificates" is run), download with `curl -LO` and pass `--csv`.

Plumer (Mother Jones, 2004) and Posner (Slate, 2012) are copyrighted, and this repository is public, so `data/sources/` is gitignored. That includes the reference graphs in `data/sources/electoral_college/reference/`: their units cover the passages, so they contain the full text.

Sources are not essays, so the reference uses its own format, `source_graph/0.1` (`src/argument_graph/source_graph.py`), rather than the essay graph. The first draft used essay roles and the single-rooted eRST tree, which left the Federal Register sheet with no support links at all and most units of the opinion pieces outside any reason (50 of 71 for Plumer, 40 of 71 for Posner).
- **Units** still cover the text with exact quotes. Each records its paragraph number and one of seven types: `thesis`, `claim`, `fact`, `example`, `concession`, `opposing_view` or `framing` (questions, headings, asides). Stance is the source author's own.
- **Edges** run from a passage (one or more units) to a single unit, so a whole block of evidence counts as the reason. The types are `supports`, `opposes` (the author answers an opposing view), `concedes` (granted, but the claim holds anyway) and `elaborates` (detail, not a reason).
- **The validator** checks coverage, paragraph numbers, that type and stance agree, and that edge targets make sense. Every concession and opposing view must be linked. In a source with a thesis, every non-framing unit must be in an edge. A fact sheet with no thesis needs no links.

There is one graph per source: S1 Federal Register (24 facts grouped by topic, no argument); S2 Plumer (71 units, 20 edges); S3 Posner (71 units, 27 edges). In S2 and S3 every non-framing unit is in an edge; 56 of 58 and 60 of 66 are in a supports, opposes or concedes passage. The remainder are restatements, a continuation, or detail of the opposing view. Opposing authors stay separate, so neither side becomes the "correct" answer. Claude drafted them on 2026-09-26: `reference/segmentation/` fixes the units, `reference/annotations/` gives types and edges, and `reference/build_reference.py` builds and validates them. They are not yet reviewed. View them with:

```sh
D=data/sources/electoral_college
PYTHONPATH=src python3 -m argument_graph.render_source_html --records $D/source_records.jsonl \
  --graph $D/reference/S1.source_graph.json --graph $D/reference/S2.source_graph.json --graph $D/reference/S3.source_graph.json \
  --output $D/reference/source_graphs.html
```

`data/annotations/reference/electoral_college_expectations.json` (committed) lists the assignment's explicit requirements, each with its exact quote: a letter to a state senator, a position, a claim, counterclaims, evidence from several sources without over-relying on one, and a multiparagraph essay.

## Align student graphs with the sources (Phase C prototype)

`src/argument_graph/align.py` links each unit of a student graph to the source-graph units it draws on, and says how faithfully:
- `quote`: copies the source's wording.
- `paraphrase`: the same proposition in other words.
- `distorted`: based on a source but changed: reversed, a wrong number, name or date, a misused example, or an opposing view presented as the author's.
- `related`: uses source content to assert something the source does not say.
- `none`: no source basis.

The three sources total about 2,000 words, so the model judge sees every source unit, with source, paragraph number, type and the author's stance, rather than a retrieved shortlist. Of the student essay it sees only the text and unit quotes, never roles, stances or relations, so gold graphs can be used as input without leaking annotations. Answers are validated: every unit is aligned exactly once, links point to real source units, linked labels have links, and a distortion states what changed. Failed checks go back to the model for up to 3 attempts, and output is never repaired silently. A word-overlap baseline (idf-weighted cosine) costs nothing and serves as the comparison.

```sh
G=data/annotations
PYTHONPATH=src python3 -m argument_graph.align run --records data/processed/electoral_college_v6/pilot.jsonl \
  $(for f in $G/argument_graphs/*.json $G/argument_graphs_pilot_check/*.json; do echo --graph $f; done)
PYTHONPATH=src python3 -m argument_graph.align score --run-dir data/runs/align/<run folder>
```

The run writes `data/runs/align/align-0.1_<model>_<effort>_<hash>/`: the system prompt, and per essay `<id>.align.json` and `<id>.log.json`. The hash covers the prompt, schema, model, effort and source listing. At Opus 5, effort `high`, the 8 gold essays are estimated at about $2 (about 6k input tokens per essay). `score` compares the judge and the baseline with the gold. It reports 5-way label accuracy, source-use F1 (any source basis versus none), link precision, recall and F1 for quote, paraphrase and distorted units, agreement on which source is used, and distortions found and falsely flagged. Each system is scored only on the essays it has aligned.

**Gold alignments** (`data/annotations/alignments/`, committed: student text and source unit IDs only) cover all 302 units of the 8 gold essays. The counts are 136 none, 59 related, 58 paraphrase, 35 quote and 14 distorted. Claude wrote them on 2026-09-26, before any judge run, and they are not yet reviewed. Word-overlap candidates were shown during annotation as a reading aid only. The 14 distortions include the reversed "certainty of outcome" claim, the misused Nixon example, the rule that a tie is decided by the House being given to the electors, "5,559 votes" with Hawaii dropped, the tie rule applied to Wyoming's electoral votes, and a Louisiana episode paraphrased into something else.

**Baseline** (word overlap, all 8 essays): label accuracy 0.47, source-use F1 0.65, link precision 0.93 but recall 0.26 (F1 0.41), and 0 of 14 distortions found. It finds copied text reliably and misses paraphrase and every distortion, which is what the judge is for.

**Judge, first run** (`align/0.1`, Opus 5, effort `high`, 2026-09-26). All 8 essays aligned on the first attempt, for about $1.01 (74k input and 26k output tokens).

| | Label accuracy | Source-use F1 | Link precision | Link recall | Link F1 | Same source | Distortions found | False distortions |
|---|---|---|---|---|---|---|---|---|
| Word-overlap baseline | 0.47 | 0.65 | 0.93 | 0.26 | 0.41 | 1.00 | 0 / 14 | 0 |
| Judge | 0.67 | 0.83 | 0.53 | 0.87 | 0.66 | 0.91 | 8 / 14 | 5 |

The judge finds the right passage. When the judge and the gold both link a unit, they share a source unit 99% of the time; the judge just lists more neighbouring units (1.78 per linked unit against the gold's 1.32). Most of the gap is at label boundaries that neither the prompt nor the gold states clearly:
- **`none` vs `related` (64 units: gold none, judge related or paraphrase).** The judge links students' own stances, evaluations and calls to action to a source's thesis ("Moving to popular vote will fix all of these problems" to Plumer's "Abolish the electoral college!"). The gold is not consistent here either: it links "We should abolish the Electoral College" to Plumer but not "try to topple down the un-democratic roots".
- **`related` vs `distorted`.** In 3 of the 6 missed distortions, the judge's note names the change ("'bound to happen soon' is the student's escalation") but it chose `related`. Overstatement has no stated rule.
- **Contradicting the passages.** Several of the 5 false alarms are defensible. "The electors… vote what the state wants" does contradict Plumer ¶10–11, and "lose interest in voting" goes beyond Posner's "less incentive to pay attention", in a view he reports only to rebut. The gold may be too lenient on these.

These are 8 essays whose gold was written by Claude and not yet reviewed, so the figures are a first reading.

**Rules R1–R3 and gold revision (2026-09-26).** The three boundaries are now written rules, in `data/annotations/alignments/GUIDELINES.md` and in the judge prompt (`align/0.2`):
- **R1.** `related` needs specific source content; a stance, evaluation or call to action that only agrees with a source is `none`.
- **R2.** Overstating a specific source claim is `distorted`.
- **R3.** Asserting what a passage contradicts is `distorted`, unless another source supports it.

The gold was revised by applying the rules to all 117 `related` and `paraphrase` units, which changed 12: 9 moved to `none` under R1, 2 to `distorted` under R2 and 1 under R3. Each change is logged with its rule in the file's `change_log` (`confirmed_by: null`). In three places the gold was kept against the judge; they are recorded as clarifications in the guidelines. The labels are now 145 none, 55 paraphrase, 50 related, 35 quote and 17 distorted.

The revision was made after seeing the judge's answers. To check it does not simply copy them, the first run was re-scored against the revised gold. Label accuracy went from 0.67 to 0.66, source-use F1 from 0.83 to 0.80, and distortions from 8 of 14 found (5 false) to 10 of 17 (3 false). These 8 essays now count as development data for the judge; a fair estimate needs new gold essays.

**Judge `align/0.2`** (Opus 5, effort `high`, 2026-09-26; all 8 essays on the first attempt, about $1.05), scored against the revised gold:

| | Label accuracy | Source-use F1 | Link precision | Link recall | Link F1 | Same source | Distortions found | False distortions |
|---|---|---|---|---|---|---|---|---|
| Word-overlap baseline | 0.46 | 0.62 | 0.93 | 0.26 | 0.41 | 1.00 | 0 / 17 | 0 |
| Judge `align/0.1` | 0.66 | 0.80 | 0.53 | 0.87 | 0.66 | 0.91 | 10 / 17 | 3 |
| Judge `align/0.2` | 0.83 | 0.94 | 0.64 | 0.89 | 0.75 | 0.93 | 11 / 17 | 4 |

The largest remaining disagreement, 19 units, is `related` (gold) against `paraphrase` (judge): previews, summaries and small inferences such as "the larger the population, the more electoral votes". Both labels mean source use, so this boundary matters less.

Distortion is still the hardest label.
- **Missed:** "swing states, the states that have a bigger weight". Also "the majority of the citizens wants him", where the judge's note recognises the plurality-to-majority change but the label is `related`.
- **Arguably right:** two of the four false alarms apply the rules more strictly than the gold. These are "electors can vote for any candidate", against Plumer's "occasionally", and "unbiased electors", against party-chosen electors.

Because a flagged distortion is a candidate misconception, it should go to review rather than straight to a finding. That matches plan section 5, Phase C. These figures come from essays that shaped the rules and the gold.

**Held-out alignment gold (2026-09-26).** For a fair measurement, `align/0.2` is frozen, and gold alignments were written for the 6 pilot-check essays that have no gold graph. These are 95A6F680F078, 6AB345CECE0B, 97DD2D770B03, AD0F893FA473, 45C70D14F6F3 and F00FF00D5C8F: 290 units, labelled 175 none, 47 related, 31 paraphrase, 24 quote and 13 distorted. As the user chose, the units are the model's own v0.3 extraction, copied to `data/annotations/alignments/student_graphs/`. This tests extraction and alignment together, as the pipeline would run. Because the model's graphs have now been read, gold graphs should not later be written for these essays, so the held-out extraction test stays at 4 essays. The gold was written under `GUIDELINES.md` before any judge run on these essays. Each file records `provenance.split` (`development` or `held_out`), and `align score` reports the two splits separately. One consistency fix to the development gold came out of this work: 671D0569C835 x4, a bare "not democratic" evaluation, is now `none` under R1, as are x17 and x45. It is logged, and it moves the development judge score from 0.834 to 0.831.

**Held-out result** (frozen `align/0.2`, 6 essays, 2026-09-26, about $0.94; one essay needed a retry):

| | Label accuracy | Source-use F1 | Link precision | Link recall | Link F1 | Same source | Distortions found | False distortions |
|---|---|---|---|---|---|---|---|---|
| Baseline, held-out | 0.55 | 0.62 | 0.85 | 0.25 | 0.39 | 0.92 | 0 / 13 | 0 |
| Judge, development (8) | 0.83 | 0.94 | 0.63 | 0.89 | 0.74 | 0.93 | 11 / 17 | 4 |
| Judge, held-out (6) | 0.83 | 0.91 | 0.52 | 0.95 | 0.67 | 0.82 | 10 / 13 | 7 |

Label accuracy on new essays matches the development figure, so the rules generalise rather than fitting the essays they came from. Recall of source use and of distortions is high: 95% of gold links and 10 of 13 distortions. Precision is lower. The judge lists extra neighbouring source units, and it flags more distortions. Five of the seven extra flags are garbled student sentences that the gold reads charitably and the judge reads literally ("your votes are being represented equally", presumably "unequally"; "Al Gore lost because he received the most popular votes"). The other two are borderline. For a system whose distortion flags go to human review, this is the safer direction of error. Agreement on which source is used is lower on held-out essays (0.82), because students there mix sources more. This is one run on 6 essays, with Claude-written gold that is not yet reviewed.

Writing the gold also changed two things. The judge now labels a unit by what it asserts even when it repeats an earlier point: an introduction's preview or a conclusion's summary of a source-based point would otherwise hide source use. And one note in the reviewed F3B4F60CE90C gold graph was corrected: Posner ¶21 does say large states get more attention, so the student's error is "the only ones". The change is logged in the file with `confirmed_by: null`.

## Findings for review (Phase C, first version)

`src/argument_graph/findings.py` combines an essay's graph, its source alignment, the source units and the assignment's expectations into findings. It uses rules only, with no model calls. Every finding lists the student units and source units it rests on, a rationale, which earlier stage it depends on (`extraction`, `alignment`), and `review_status: needs_review`. These are candidates to check, not diagnoses.
- **`possible_misconception`:** every unit the judge aligned as `distorted`, with the source passage and the judge's note on what changed. It records whether the student asserts the unit or only reports it.
- **`unsupported_claim`:** a claim the student offers as a reason (the root, or the satellite of an explanation relation) that gets no support in the graph and has no basis in the sources. Support counts if it arrives directly, through a list or split-unit partner, or through a later unit that restates the claim. Conditions, frames and other fragments of a claim are not judged on their own.
- **`missing_required_content`:** checks against the explicit expectations: a claim (E3), a counterclaim (E4), use of the sources (E7), at least two sources (E5), no single source above 75% of source-based units (E6, provisional, judged only from 4 such units), and at least three paragraphs (E8). The letter form (E1) and taking a position on the given question (E2) are not checked.

```sh
PYTHONPATH=src python3 -m argument_graph.findings --align-run data/runs/align/<run folder> --records data/processed/electoral_college_v6/pilot.jsonl
PYTHONPATH=src python3 -m argument_graph.render_findings_html --findings-dir data/runs/findings/<run folder> --records data/processed/electoral_college_v6/pilot.jsonl
```

The review page shows the essay with units tinted by source use, the requirement checklist, source use per source, and each finding with the student's words beside the source passage. It quotes the passages, so it stays in the gitignored `data/runs/`.

**First run** (the 14 essays aligned by `align/0.2`, 2026-09-26): 32 possible misconceptions, 5 unsupported claims and 7 unmet requirements. Five of the 7 unmet requirements are over-reliance on one source (E6). One is E0737CDC1E99, which takes 21 of 27 source-based units from Posner. The other two are both in C0BA22AD7F2A: it uses only Plumer (E5) and has two paragraphs (E8). The first unsupported-claim rule flagged 36 units, mostly fragments of claims (conditions, frames, previews); the rule was narrowed to reasons offered in the graph, which left 5. They include "all the electors care about is just the winnings" and "we would have a better economy". How good these findings are has not been measured. The misconception candidates inherit the judge's distortion precision (about 60% held-out), and the other findings depend on extraction quality. A reviewed sample is the next check.

## Generate a graph in the browser

```sh
export ANTHROPIC_API_KEY=...
PYTHONPATH=src python3 -m argument_graph.web        # then open http://127.0.0.1:8000
```

A local page where you paste an essay question and an essay, and get its argument graph in the same viewer as `render_graph_html`. It runs the same extraction as `student_graph.py` (current prompt, validation and retries), so an essay takes one to four minutes and roughly $0.30 to $1 at Opus 5, effort `high`. Every request is saved under `data/runs/web/<time>-<hash>/`: `input.json`, `log.json` (every attempt), `summary.json` (tokens, estimated cost, configuration) and `graph.json` when extraction succeeds. A failed extraction shows the stage and the checks that failed, never a partial graph. The server listens on 127.0.0.1 only. `--port`, `--model`, `--effort` and `--output-dir` change the defaults. The graph is an unreviewed model extraction; the development and pilot-check results above describe how far to trust it.

## Score extracted graphs

```sh
PYTHONPATH=src python3 -m argument_graph.evaluate \
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

### Pilot-check results (v0.3, frozen)

One run of v0.3 on the 10 pilot-check essays, which had not been used for tuning, scored 2026-09-26 against the four pilot-check gold graphs and against PERSUADE. All 10 were extracted (cost $4.93, plus about $0.40 for two essays that failed before the whitespace fix and were re-run). Development figures for the same run are shown for comparison.

| Split | Exact unit F1 | Boundary F1 | Root | Attachment | Labelled | Stance | Derived F1 | PERSUADE role | PERSUADE element F1 |
|---|---|---|---|---|---|---|---|---|---|
| Development (4 gold / 11 essays) | 0.79 | 0.91 | 3/4 | 0.80 | 0.72 | 0.97 | 0.80 | 0.73 | 0.59 |
| Pilot-check (4 gold / 10 essays) | 0.83 | 0.94 | 3/4 | 0.76 | 0.67 | 0.82 | 0.66 | 0.70 | 0.62 |

Most of the stance gap comes from facts the writer attributes to a source ("According to Source 2, …", "as seen in the article, …"). The model marks them `reported`, following the prompt's definition ("attributed to others"). The gold marks them `endorsed`, because the writer uses them as their own evidence. Counting `reported` as `endorsed` raises pooled stance agreement from 0.83 to 0.90 and leaves derived edges unchanged. The user has since decided on `endorsed` for such facts (plan section 4.1); the next prompt version must say so. The drop in derived F1 is structural: explanation-justify was labelled causal-cause or causal-result five times, a confusion v0.2 had removed on the development essays. The root miss (671D0569C835) is the root-choice ambiguity noted for the pilot-check gold. The pilot-check essays have now been used. Any later prompt change needs a new held-out sample drawn from the remaining electoral-college essays.

## Read essays with their argument tree

```sh
PYTHONPATH=src python3 -m argument_graph.render_html \
  --records data/processed/electoral_college_v6/pilot.jsonl \
  --essay <development example_id> ... \
  --output data/processed/electoral_college_v6/viewer/development_viewer.html
```

A self-contained HTML page: the essay with spans highlighted by role beside its argument graph, built from hierarchy candidate links. The Graph tab draws spans as nodes with arrows child → parent (left-to-right or top-down; scroll to zoom, drag to pan); the Outline tab shows the same tree as nested cards. Hovering either side highlights its counterpart; clicking jumps to it. Arrow keys switch essays. Add `--essay <example_id>` (repeatable) for specific essays and `--include-unannotated` to keep Unannotated spans.

## Test

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Tests cover inclusive endpoints, ambiguity, Unicode/whitespace index mapping, invalid spans, repeated raw IDs, missing supplementary joins, unavailable annotations, hierarchy candidates, model-input leakage, a second dataset-shaped fixture, deterministic essay-level splitting, offset-window recovery, order-conflict rejection, and Unannotated overlap removal. Graph tests cover contract validation, derived support/attack edges, extraction with a stubbed model (quote location, retries, failures, pilot-check refusal), and the scorer.
