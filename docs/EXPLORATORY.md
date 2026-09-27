# Exploratory work: sources, alignment and findings

This work is outside the current scope (student graph extraction). It is kept because it runs and is tested, and because misconception detection may return to it. Nothing here has been reviewed by the user except where stated.

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
