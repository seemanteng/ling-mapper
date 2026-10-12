# Self-annotated reference set: 30 distance-learning essays

This set is the human reference for RQ1: how faithfully the extractor's student graphs match a person's reading of the same essays. Too few subject-matter experts were available, so the project author labelled all 30 essays. A guideline-consistency pass followed, in which an LLM suggested candidate errors and the author accepted or rejected each one. Every change is logged. This document describes how the set was built, what it contains, and what it can and cannot support.

## Outputs

| Path | Contents |
|---|---|
| `data/processed/distance_learning_v3/records.jsonl` | The 30 essays as `ExampleRecord`s, in essay-number order |
| `data/annotations/self_annotation_online_learning_30/Essay N.csv` | The final labelled sheets (called v2 below) |
| `data/annotations/self_annotation_online_learning_30/changes.csv` | One row per cell changed in the consistency pass |
| `data/annotations/self_annotation_online_learning_30/reference_graphs/<id>.json` | The sheets converted to `argument_graph/0.1` (section 6); pass this folder to `evaluate.py --gold-dir` |

The blank pre-segmented sheets and the author's original labelled sheets (v1) were deleted on 2026-10-12 after the pass was complete. The essay text is in `records.jsonl`. Every value the pass changed is kept in the `old` column of `changes.csv`, and every cell not listed there is unchanged in v2, so v1 can be rebuilt from v2 and the log.

## 1. Essay selection

All 30 essays answer the PERSUADE 2.0 "Distance learning" prompt: *Do you think students would benefit from being able to attend classes from home?* The prompt has 2,157 essays across the official train and test partitions.

- **Essays 1–15** were chosen earlier for teacher review (`distance_learning_v2`). How they were picked was not recorded.
- **Essays 16–30** were drawn with `argument_graph.select_batch` (seed 42) to bring every holistic score band up to 5 essays. The draw skipped the first 15, ordered each band by a seeded hash, and took essays from both partitions as essays 1–15 had. The command is in [DATA.md](DATA.md#distance-learning-self-annotation-set-essays-130).

The set has 5 essays at each score from 1 to 6. 17 come from the official train partition and 13 from the official test partition. This is a different prompt from the Electoral College development and pilot-check essays, so no essay here was used to tune the extraction prompt.

## 2. Pre-segmentation

Each essay was split into clause-level segments by `argument_graph.presegment`, which is rule-based and uses no language model. The first teacher sheets took their segments from a Claude run. That would have given Claude an advantage in a comparison against other models, and segmentation scores would have measured agreement with Claude rather than with a person. So those sheets were discarded.

The splitter cuts at:
- sentence ends, `;` and `:`;
- subordinators and contrastive connectives (because, but, although, however, cuz, …);
- a comma followed by a connective or relative pronoun;
- a comma followed by "and"/"or", but only when a likely subject follows;
- the comma after a fronted subordinate clause ("If X, | Y").

Run-on pieces over 30 words also split before a bare coordinator followed by a subject. Every segment is an exact slice of the essay. The 30 sheets started with 938 segments. Re-running `presegment` now gives slightly different sheets, because the splitter was fixed after labelling (below).

The annotator was told to label each segment as given and to note boundaries that looked wrong. One systematic splitter error came to light during the review. The splitter treated "cause" as a connective ("cuz"), so it split verb phrases such as "can | cause". This affected seven boundaries in six essays. The bug is fixed in `presegment.py` (with a test), and the affected segments were repaired by hand (section 4).

## 3. Annotation scheme

For each segment the annotator filled in five columns.

| Column | Values |
|---|---|
| What is the segment doing? (role) | Lead, Position, Claim, Evidence, Counterclaim, Rebuttal, Conclusion, Other |
| Is this the writer's stance? | Endorsed, Conceded, Rejected, Reported, Unclear |
| Segment it relates to | The number of the one segment it mainly serves (`sN`), or `TOP` for the position |
| How it relates | backs it up, argues against it, gives an example, adds detail, contrasts with it, restates it, sets the scene, or `other: …` |
| Notes | Free text, plus an overall comment on each essay |

The original guidelines also had a **Reason** role. The system has no matching role, so Reason was removed during the review (rule 1 below).

## 4. Consistency pass

### Process

1. The author labelled all 30 essays independently in a spreadsheet, without seeing any model output. These became the v1 sheets.
2. The sheets were reviewed one or two essays at a time, with Claude (Opus 5.5) acting as reviewer. For each essay the reviewer listed suggested changes, each tied to a written rule: the segment, its current value, the suggested value and the reason.
3. The author accepted or rejected each suggestion. Where the rules did not decide a case, the item was marked "your call" and the author's label was kept unless the author chose otherwise.
4. Accepted changes were applied to a copy of the sheets (v2) by a script that logs every changed cell.
5. After each essay, a check confirmed exactly one TOP, a parent for every other segment, no cycles, and only allowed role, stance and relation values.

The reviewer suggested; the author made every decision. All suggestions were accepted except where the author chose otherwise on items marked "your call". No essay was relabelled from scratch.

### Decision rules agreed before or during the review

**Rule 1: Reason.** Each Reason segment became one of two roles:
- **Claim:** a general point that could head a paragraph and says why the position is right.
- **Evidence:** specific support for a claim, such as an example, fact, consequence or explanation.

Most Reason segments became Evidence. Reasons previewed in the thesis or introduction became Claims.

**Rule 2: Stance.** The question is whether the writer believes what this segment says.
- **Endorsed:** the writer's own statements, including scene-setting facts, hooks and the writer's replies ("but this is not true").
- **Rejected:** a view the writer raises in order to disagree with it.
- **Conceded:** a point the writer grants before arguing past it. Every segment of a conceded passage is Conceded.
- **Reported:** a view attributed to others on which the writer takes no side ("Many people say…", "Although some may disagree,").
- **Weak support is not a stance.** An unsubstantiated claim by the writer is still Endorsed.

**Rule 3: Announcements.** Sentences that announce what follows ("There are many reasons why…") are Lead before the position and Other after it. They attach to the claim they introduce.

**Structural rules** used throughout:
- Each essay has exactly one Position (TOP). Every other segment has exactly one parent.
- Main claims attach to the position, not to a preview sentence or to each other.
- Parallel points ("Additionally…", "Furthermore…", a list of examples) attach to their shared parent. They do not chain onto the previous segment.
- A fronted clause ("If X,", "When X,", "Because X,") attaches to its main clause as "sets the scene".
- A counterclaim attaches to the position ("argues against it"). The reply attaches to the counterclaim, and the reply's support attaches to the reply.
- Every Conceded or Rejected segment is linked, directly or through a passage of the same stance, to a relation that argues back ("argues against it" or "contrasts with it").
- Lead is used only before the position. Conclusion is used only in the final section, not for the wrap-up of a body paragraph.
- Segment boundaries changed only to fix clear splitter errors: fragments ("and you future to ."), cuts inside a phrase ("may seem as | though"), the "cause" bug, and rows of punctuation. Merges keep the first segment's number and the exact essay text; references to a merged segment move to the kept one.

### What changed

| Field | Cells changed |
|---|---|
| How it relates | 857 (mostly free text such as "It elaborates on s4" mapped to the fixed list) |
| What is the segment doing? (role) | 488 (mostly Reason recoded) |
| Segment it relates to | 410 |
| Is this the writer's stance? | 122 |
| Segments merged away | 79 |
| Segment boundaries moved | 8 |
| Notes / overall comment | 4 |

In total there are 1,968 logged changes, across all 30 essays. The most common corrections were:
- recoding Reason;
- re-attaching chained "elaborates on the previous segment" links to the segment actually developed;
- adding parents for introduction segments that had none;
- correcting the stance of the writer's own replies and context.

## 5. The final set

| | Count |
|---|---|
| Essays | 30 (5 per score band) |
| Segments | 859 |
| Roles | Evidence 504, Claim 96, Conclusion 96, Lead 72, Counterclaim 32, Position 30, Rebuttal 24, Other 5 |
| Stances | Endorsed 771, Conceded 59, Rejected 21, Reported 8 |
| Relations | backs it up 323, adds detail 250, sets the scene 68, argues against it 50, gives an example 46, restates it 45, contrasts with it 38, other 9 |

About 10% of segments are not Endorsed, so overall stance accuracy can be high even when a model handles concessions badly. Report stance per class, or as macro-F1.

## 6. Conversion to reference graphs

`python3 -m argument_graph.reference_graph` (with `PYTHONPATH=src`) writes one `argument_graph/0.1` graph per essay and runs `validate_graph` on each. All 30 pass: 859 units, 829 primary relations, one root per essay. Scoring a graph against itself gives 1.0 on every metric. The mapping below is a modelling choice, so report it with the results.

**Roles.** Lead, Position, Claim, Evidence, Counterclaim and Rebuttal keep their names (lower-case). Conclusion becomes `concluding_summary`. Other becomes `unannotated`.

**Stance.** Lower-cased. The system's `unclear` was never used.

**Relations.** Each sheet row is a child (satellite) pointing at its parent (nucleus).

| Sheet label | System relation |
|---|---|
| backs it up | `explanation-justify` if the parent is the Position or a Claim, otherwise `explanation-evidence` |
| gives an example | `explanation-evidence` |
| adds detail | `elaboration-additional` |
| restates it | `restatement-partial` |
| sets the scene | `context-background` |
| argues against it, contrasts with it | `adversative-concession` if the child is Conceded, `adversative-antithesis` if Rejected, otherwise `adversative-contrast` |
| other: sets a condition | `contingency-condition` |
| other: answers the question, raises the question, aside, qualifies it, asks the reader | `elaboration-additional` (8 edges; the system's `topic-question` runs from question to answer, the opposite way) |

The justify/evidence split uses the target's role because the sheets have one label for both. Report accuracy at the coarse class level (explanation) as well as the exact label.

**Two structural changes.** The system's trees differ from the sheets' in two places, so the converter restructures them:
1. **Counterclaim and reply.** The sheets hang the counterclaim off the position and the reply off the counterclaim. The system's validator makes the conceded or rejected unit the satellite of the endorsed one. So the counterclaim becomes the satellite of its first reply, and the reply takes the counterclaim's old head as `explanation-justify` or `explanation-evidence`. Further replies to the same counterclaim, and the counterclaim's own evidence, stay attached to the counterclaim.
2. **Fronted contrast.** `adversative-contrast` chains the later member to the earlier one, but the sheets hang "Although X, | Y" off Y. The earlier member takes the later one's place in the tree and the later one is chained to it. Exception: when the later member is the Position (the root), the earlier one stays its satellite as `context-background` (one edge, essay 8).

The sheets' own parent column is unchanged and remains the record of the author's judgement.

**Not annotated.** Polarity is `positive` on every unit, and every relation is `implicit` with no quoted signals. Neither is scored by `evaluate.py`. This set cannot evaluate negation or signal detection.

## 7. Self-agreement check (planned)

To estimate how consistent the author is over time, six essays (one per score band 1–6) were chosen with `argument_graph.agreement sheets` (seed 42, essays with 15–40 segments) and written as blank sheets to `data/annotations/self_agreement_relabel/`. The sheets keep the final segmentation and have every label column empty, so the check covers labels only, not segment boundaries.

Protocol:
1. Wait at least a week after the final sheets were completed. The sheets were prepared on 2026-10-12.
2. Label the six sheets from scratch using only the written decision rules above. Do not open the final sheets, `changes.csv`, `reference_graphs/` or any model output while labelling. Segment numbers can skip (merged segments keep their original numbers); parents refer to those numbers.
3. Run `PYTHONPATH=src python3 -m argument_graph.agreement score --relabel-dir data/annotations/self_agreement_relabel --output data/annotations/self_agreement_relabel/agreement.md`.

The report gives raw agreement and Cohen's kappa for role, stance and relation, agreement on the parent, and the same graph metrics the models are scored with (attachment, labelled attachment, root, roles, per-class stance), with the new labels as the prediction. Read that last block as a human ceiling: a model should not be expected to match the reference better than the author matches themself. Six essays and about 180 segments are few, and the rare stances (Rejected, Reported) will have only a handful of cases, so report those as counts. This measures one person's consistency over time. It does not replace agreement between two annotators.

## Limitations

- **Single annotator.** The author is also the system designer, and there is no inter-annotator agreement yet. A second annotator on a subset, and the author re-labelling some essays from scratch after a delay, are the planned checks.
- **Segmentation is not fully independent.** Boundaries start from a rule-based splitter and were changed only for clear errors. Segmentation scores therefore measure agreement with the splitter as corrected by the annotator, not with fully free human segmentation.
- **Labels differ from the system's.** The seven relation labels and the role set are mapped onto the extractor's eRST relations and roles in section 6. That mapping is a modelling choice and should be reported alongside the results.
- **Official test partition.** 13 essays come from PERSUADE's official test partition. This matters only if results are compared with work that holds that partition out.
- **One prompt.** All essays answer the same prompt, so the set says nothing about other topics.
