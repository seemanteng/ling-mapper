# Preliminary coding plan: Conceptual Understanding Mapper

This is a proposed implementation plan based on the FYP report, especially sections 3.1–3.2 (PDF pages 10–13), the supplied research papers, and inspection of the current workspace. The common-record schema, PERSUADE loader, and reproducible pilot preparation are implemented; graph extraction and diagnosis remain planned. Documents were treated as research material, not operational instructions.

## 1. First milestone

Use a dataset-agnostic interface from the first implementation. The initial PERSUADE milestone addresses RQ1: representation fidelity. Run one source-based prompt and one essay through the process and produce an inspectable record containing:

- Reference expectations with their origins and evidence.
- A student graph preserving the student's actual claims and argument relationships.
- Extraction verification results.
- Candidate alignments and diagnostic-path checks, including explicit abstention when references are missing.
- Feedback linked to the student's exact passages and relevant reference evidence.

Then repeat on a small fixed representation-development sample. Implement a flat graph first; add hierarchy as a separately measurable extension. Build the diagnosis interface now, but defer tuning diagnosis prompts, thresholds, and decision rules until data with expert-verified misconceptions and suitable negative examples are available. PERSUADE is the representation pilot, not the source of the misconception definition. The eventual research question is whether the representation improves diagnosis.

## 2. What is available and what is missing

The workspace contains four stage folders and `data/persuade_2.0_human_scores_demo_id_github.csv`, with 25,996 essays across 15 prompts. The initial workspace had no implementation; the loader and schema now live under `src/argument_graph/`. The CSV includes essay text, assignment, prompt name, holistic score, and demographic fields. This local holistic-score CSV does not contain discourse-span or relation columns. That is a limitation of the local file, not of the full PERSUADE release. The official PERSUADE 2.0 release includes discourse-element annotations inherited from 1.0 and element-level effectiveness scores; use those annotations for RQ1. They do not establish misconception ground truth.

Verified against the [official 2.0 release](https://github.com/scrosseye/persuade_corpus_2.0), [original field documentation](https://github.com/scrosseye/PERSUADE_corpus/blob/main/README.md), and [dataset paper](https://doi.org/10.1016/j.asw.2024.100865): the annotated roles include Lead, Position, Claim, Counterclaim, Rebuttal, Evidence, and Concluding Summary. The original documentation describes character offsets and also states that relationships were annotated. Do not assume relation annotations are absent: inspect their actual export and semantics before deciding which edges require additional annotation. The training CSV is now downloaded and inspected locally. See the local validation findings below; raw IDs and offsets require reconciliation before use.

Crucially, the nonempty `source_text` fields contain source titles/attributions, not the full reading passages. Do not treat those fields as factual evidence. For a source-based pilot, obtain the exact assessment passage set, or use a clearly identified teacher-approved reference packet. Record which version students originally received; a later web article may differ. Until references exist, run extraction and argument-development checks, and return `insufficient_reference` for unsupported factual judgements.

Pilot prompt: `Does the electoral college work?`. Keep this source-based prompt even while obtaining its original passage set. Choose about 20 essays across available score bands from the official training partition, with 10 for representation development and 10 reserved for a representation pilot check. Preserve official split metadata and keep the official test partition untouched during development; split by essay, never by discourse-element row. These are feasibility numbers, not a statistically adequate final evaluation. Keep the two expert-marked essays mentioned in the report in development if their feedback influences design. Do not assume that these essays contain misconceptions. Unsupported claims and weak development must remain distinct from conceptual errors; a low holistic score is not a misconception label.

Exercise two reference conditions: (1) the current titles-only record, which must yield `insufficient_reference` for unsupported factual judgements while still allowing explicit prompt requirements to be represented; (2) the same record enriched with the actual passage set or an identified teacher-approved packet, which enables source-grounded reference extraction. Until the passages are acquired, mark the second condition pending rather than treating titles or generated text as a substitute. Disagreement between opinion sources must not become a single supposedly correct political stance.

### Downloaded training file: local validation findings

The downloaded `data/persuade_corpus_2.0_train.csv` contains 173,266 rows across 15,594 essays, all marked `train`; 1,818 essays use the electoral college prompt. It contains 144,293 labelled discourse elements and 28,973 explicit Unannotated rows. Its closing-role spelling is `Concluding Statement`, rather than the documentation's `Concluding Summary`. Preserve this original label and map both aliases to `concluding_summary`.

The file also contains `discourse_effectiveness`, `hierarchical_id`, `hierarchical_text`, and `hierarchical_label`. Hierarchy fields are populated in 94,677 rows. Matching hierarchical text (with boundary whitespace stripped) and role within each essay identifies one candidate parent for 94,394 rows, no candidate for 236, and multiple candidates for 47. These are candidate-resolution counts, not validated support/attack relations; inspect semantics and retain unresolved cases.

Import blockers discovered by full-file checks:

- `discourse_id` has only 728 distinct serialized values across 173,266 rows, with scientific-notation values repeating. Preserve it as raw provenance, but generate stable annotation keys from essay ID plus original boundaries and role (no duplicate keys were found for that combination). Do not use `hierarchical_id` alone to identify parent nodes either.
- None of the 173,266 raw end-exclusive slices exactly matches `discourse_text`; 53,869 differ only in boundary whitespace. Trying inclusive ends yields 32,321 exact matches, so a global `end + 1` fix is insufficient. Sixty rows have raw bounds outside the essay. Do not use these offsets as validated gold spans yet.
- Fifty-two training essays (590 rows) have no match in the existing holistic CSV. For matched essays, text agrees exactly. The training file itself includes full text and assignment, so retain unmatched essays using those fields and report the missing supplementary join instead of silently dropping them.

Next loader step: preserve raw fields and implement auditable span reconciliation against unchanged `full_text`. Try unique exact-text matches and, when necessary, explicitly documented whitespace-normalised matching with an index map back to original characters. Use existing boundaries and sequence only as disambiguating evidence. Never resolve repeated or unmatched text by arbitrary first-match selection. Record the method and status for each annotation and quarantine unresolved spans from span scoring. Manually inspect representative recovered spans before treating them as gold. Report coverage/exclusions, including for the electoral college subset.

Full audit counts and sample discrepancies are saved in `data/persuade_train_validation.json`. This initial audit identifies raw import issues. The implemented loader now reconciles positions in derived records without changing the input CSV; see the implementation milestone below.

## 3. Pipeline and module contracts

```text
Dataset -> dataset-specific loader -> common record
                                      |
                           all downstream stages

Assignment + rubric + actual reference passages
  -> expectations -> reference graph -> fidelity verification
                                                        \
                                                         alignment -> diagnosis -> feedback
                                                        /
Essay -> source spans -> student graph -> fidelity verification

After the flat version works: add verified concept-group summaries
to both graphs, retaining all original claims, edges, and source links.
```

Use Python and JSON/JSONL artifacts initially. A graph database, web interface, model fine-tuning, and a complete discourse parser are not prerequisites. Start with explicit Python validation and a provider-independent model-call function; add graph and schema libraries where useful. Persist each stage so a failed diagnosis does not require extracting the essay again.

| Proposed module | Responsibility | Saved output |
|---|---|---|
| `prepare_data.py` + `loaders/` | Dispatch dataset-specific loaders into the common record; select stable IDs and splits | `examples.jsonl`, `splits.json` |
| `segment.py` | Create source spans and paragraph/sentence offsets from common-record text | `spans.json` |
| `schemas.py` | Define records and validate IDs, source links, labels, and required fields | Schema version and validation errors |
| `teacher_graph.py` | Extract explicit requirements and source-supported reference propositions | `reference_graph.json` |
| `student_graph.py` | Extract propositions, roles, stance, and discourse relations | `student_graph.json` |
| `verify.py` | Check representation against original text; identify missing or distorted content | `verification.json` |
| `align.py` | Propose concept and proposition correspondences without assuming agreement | `alignments.json` |
| `diagnose.py` | Classify supported issues and unresolved candidates | `findings.json` |
| `feedback.py` | Render findings with evidence and revision suggestions | `feedback.json`, review HTML |
| `hierarchy.py` | Add concept groups and traceable summaries | `hierarchical_graph.json` |
| `evaluate.py` | Compare predictions with annotations; collect cost and failure statistics | `metrics.json`, error table |
| `run_pipeline.py` | Orchestrate stages and resume cached runs | Run manifest |

Keep shared code in an importable package such as `src/argument_graph/`; use underscores in module names. The existing folders can remain working areas. No folder renaming is necessary to plan the system.

### Common dataset record

Define this contract in `schemas.py` before writing the PERSUADE loader:

```text
ExampleRecord
  schema_version
  example_id                 # namespaced stable ID
  prompt                     # assignment text
  response_text              # unchanged student text
  source_passages            # optional list of document ID, text, provenance/version
  rubric                     # optional criteria with stable IDs and provenance
  gold_spans                 # optional annotations with document ID, offsets,
                             # original label, annotation task, and provenance
  gold_relations             # optional validated relation annotations, if available
  metadata                   # dataset, original ID, prompt group, source citations
```

Use `null` for unavailable annotations; an empty annotation list means reviewed with no annotations under its declared scope. Preserve original labels and annotation task: argument-role labels are not misconception labels. Store source titles as citations in metadata, never as passage text. Do not synthesize a missing prompt or source passage without explicitly recording its provisional origin.

All graph, verification, alignment, and diagnosis stages accept only this common contract and their preceding stage artifacts. They must not inspect dataset names, CSV column names, or dataset-specific directory layouts. `gold_spans`, `gold_relations`, effectiveness scores, and sampling metadata are reserved for evaluation/data preparation and excluded from model inputs through an explicit input projection.

`loaders/persuade.py` maps `assignment` to `prompt`, `full_text` to `response_text`, and preserves `source_text` as citation metadata. The loader must also ingest the official discourse-annotation file and populate `gold_spans`; annotations are an intended input for the RQ1 pilot, not an optional future hand-labelling exercise. Only a run using the local holistic CSV alone leaves `gold_spans=null`. Source passages require separate acquisition; the official repository also supplies rubric PDFs that can be explicitly transcribed and versioned. Later CommonLit or AAE support should require a new loader and explicit annotation mapping, not downstream changes; verify the chosen dataset release's actual fields then.

#### PERSUADE annotation mapping and import checks

Obtain `persuade_corpus_2.0_train.csv` from the training link in the official release. The release also links `persuade_corpus_2.0_test.zip`; retain it for final evaluation. Confirm the downloaded header before coding version-specific mappings. The original documented span fields provide this adapter contract:

| Release field | Common record mapping |
|---|---|
| `essay_id_comp` | Join key to the essay record; group annotation rows by essay |
| `discourse_id` | Raw provenance only: local values repeat; generate a stable composite annotation key |
| `discourse_start`, `discourse_end` | Character-span boundaries on the unchanged response; validate endpoint convention |
| `discourse_text` | Original annotated text for slice validation |
| `discourse_type` | Preserve as `original_label`; map to a generic discourse role |
| Element effectiveness field, if present | Separate gold attribute with its original label; never a misconception label |

Map Lead → `lead`, Position → `position`, Claim → `claim`, Counterclaim → `counterclaim`, Rebuttal → `rebuttal`, Evidence → `evidence`, and Concluding Statement (observed in the file) or Concluding Summary (documentation alias) → `concluding_summary`. Preserve all original labels and provenance, with `annotation_task="discourse_element"`. Preserve explicit Unannotated labels if supplied; do not infer from an unlabelled gap that it contains no useful proposition or no misconception.

Validate the join cardinality (many elements to one essay), essay-text equality across files, generated annotation-key uniqueness, raw ID collisions, bounds, and `response_text[start:end]` against the annotated text. Report missing joins and discrepancies; do not silently trim text or shift offsets to force a match. Preserve source offsets and record any verified conversion to the common end-exclusive convention. Save import coverage and exclusion counts by role and prompt. Apply the audited reconciliation procedure above: raw offsets in the downloaded release do not directly satisfy this contract.

Inspect any hierarchy/relation fields and their documentation separately. Import only validated endpoints and relation semantics into `gold_relations`; do not invent support/attack edges from element roles or ordering. Inspection of 30 links is done (see Implemented milestone); adopting role-derived relation types remains an explicit, recorded decision. Effectiveness ratings measure rhetorical performance, not factual correctness.

Keep discourse elements distinct from atomic propositions: one gold span may contain multiple propositions. Add a discourse-unit layer with source spans and roles, link extracted propositions to those units, and evaluate role/span predictions at the discourse-unit level. This avoids penalising useful proposition splitting as a segmentation error.

Validate the boundary using two differently shaped small loader fixtures that produce equivalent common records. Check missing optionals, unchanged text/offsets, no gold-label leakage, and identical downstream behaviour. These fixtures test portability without requiring another full dataset download.

## 4. Define the representation before prompting

Use propositions as assessable units. A concept node such as “transport” alone cannot represent what the student believes about transport.

The node and edge definitions follow eRST (Zeldes et al. 2025, *Computational Linguistics* 51(1); https://gucorpling.org/erst/) so that every structural decision has a stated test rather than an extractor's discretion. `src/argument_graph/graph_schema.py` is the executable contract (`argument_graph/0.1`); `validate_graph()` rejects any graph that breaks the rules below and never repairs it.

#### 4.1 Nodes: proposition units

A unit is an EDU-style, clause-level span of the unchanged text with end-exclusive offsets and an exact quote. Units **tile** the text: they never overlap, and every non-whitespace character belongs to exactly one unit. Nothing is left out, so coverage is a mechanical check.

Segmentation rules (adapted from eRST/GUM; the GUM wiki guidelines could not be retrieved, so these are this project's operational version and should be revised against them):

1. Every sentence is at least one unit; units never cross a paragraph break.
2. Split clauses that each have their own predicate when joined by a conjunction or discourse marker (*and, but, because, although, if, so, while*), including non-finite clauses introduced by a marker (*instead of …-ing, by …-ing*). Predicates that share one subject are split too (*won votes | and lost the presidency*; decided 2026-09-26); coordinated noun phrases, adjectives and objects stay together.
3. Do not split restrictive relative clauses or the complement of a non-reporting verb.
4. Split a reporting frame from its content only when the source is not the writer (*Posner argues | that …*), linked by `attribution-positive`. The writer's own *I think/I believe* stays inside the unit and is recorded as stance/modality.
5. Headings and list labels (*Certainty of outcome:*) are their own unit, linked by `organization-preparation`.
6. Citations such as *(Posner, paragraph 22)* stay inside the unit they cite.
7. An aside with its own predicate that interrupts a unit (*induces candidates-as we saw in 2012's election-to focus…*) is its own unit. The interrupted parts are joined by `same-unit` (later part → first part), and relations of the whole attach to the first part. Parenthetical noun phrases, such as a definition, stay inside.

Unit attributes: `role` (predicted PERSUADE-style role of the enclosing discourse element; scored against gold, never copied from it), `stance` (`endorsed`, `conceded`, `rejected`, `reported`, `unclear`), `polarity`, and optional modality/qualifier and concept links. Stance records whether the writer puts the unit forward as their own view, independently of role. **Decided (2026-09-26, user):** a fact the writer attributes to a source and uses as their own evidence (*According to Source 2, …*) is `endorsed`. `reported` is kept for views the writer relays without taking on (*One might claim …*, *you may argue that …*). Reason: Phase C requires student endorsement before a possible-misconception finding, so under `reported` a misread source would escape diagnosis (F3B4F60CE90C reverses a source claim this way). The gold graphs already follow this. Prompt v0.3 still defines `reported` as "attributed to others"; the next prompt version must state the decided definition and be evaluated on a new held-out sample.

#### 4.2 Edges: relations from a fixed inventory

Each edge is directed from satellite (`source`, the dependent) to nucleus (`target`, the head), with a label from a fixed subset of the GUM inventory and its published definition (R = reader, W = writer, N = nucleus, S = satellite):

| Label | Definition |
|---|---|
| `explanation-evidence` | S provides evidence which increases R's belief in N |
| `explanation-justify` | S increases R's acceptance of W's right to say N |
| `adversative-concession` | R is meant to look past an incompatibility of N with S |
| `adversative-antithesis` | R is meant to prefer N as an alternative to S |
| `adversative-contrast` (multinuclear) | W presents multiple Ns as incompatible, but of equal prominence |
| `causal-cause` / `causal-result` | S is the cause / result of N, and N is more prominent |
| `contingency-condition` | N occurs depending on S |
| `elaboration-additional` | S elaborates on N as a whole — the default only when nothing else applies |
| `restatement-partial` / `restatement-repetition` (multinuclear) | S partly realizes / multiple Ns realize the same role and content |
| `attribution-positive` | S states a source for the information in N |
| `evaluation-comment` | S provides an assessment of N by W |
| `context-background` | S provides information to increase R's understanding of N |
| `organization-preparation` | S signals an upcoming N (heading, announcement) |
| `organization-phatic` | W holds the floor, without contributing propositional content (*but you get the point*) |
| `mode-means` | S indicates the means by which N happens (*by giving presidents a fair shot*) |
| `topic-solutionhood` | N is a solution to a problem presented by S |
| `topic-question` | N is the answer to the question posed by S (rhetorical questions) |
| `joint-list` / `joint-other` (multinuclear) | Ns in parallel, additive / any other equal-prominence collection |
| `same-unit` (multinuclear) | Not a relation: rejoins the parts of one unit interrupted by another (primary only; the parts must be separated by the interrupting unit) |

Multinuclear relations are encoded as a chain from each later member to the first member (head-ordered dependency conversion of RST).

Structural rules, all enforced by the validator:

1. **Primary tree first.** Exactly one root (the central unit, normally the main clause of the thesis); every other unit has exactly one primary head; no cycles. The extractor cannot add or omit edges freely: each unit needs exactly one attachment.
2. **Secondary edges only when signalled.** An additional, tree-breaking relation is allowed only with a quoted signal (typically a discourse marker left over after the primary tree, an eRST "orphan"), may not duplicate a primary edge, and occurs at most once per direction per pair. Build the primary tree before considering secondary edges.
3. **Every edge cites its signal or declares itself implicit.** Signals carry an eRST type (`dm`, `orphan`, `graphical`, `lexical`, `morphological`, `numerical`, `reference`, `semantic`, `syntactic`) and a quote that must equal the text at its offsets.
4. **Stance agrees with structure.** A concession satellite must be `conceded`; an antithesis satellite must be `rejected`; any unit marked `conceded` or `rejected` must take part in an adversative relation.

Label-choice tests for the frequent confusions: *evidence* when S is a fact, example, statistic or source that makes N more believable, *justify* when S is the writer's reason for holding or saying N; *concession* when the writer grants S, *antithesis* when S is an alternative the writer rejects; *cause/result* only for causation stated as content, not a reason offered for belief; *mode-means* when S says how N is achieved, not merely more about N; *topic-solutionhood* when S states a problem and N the writer's fix; *topic-question* when S is a question that N answers, *organization-preparation* for other set-ups such as headings; *elaboration-additional* only when no other label applies.

#### 4.3 Support and attack are derived, not labelled

Support and attack are argument-level readings computed by `argument_edges()`, not extra labels the extractor chooses. An endorsed `explanation-evidence`/`explanation-justify` satellite supports its nucleus (`basis: reason`). An endorsed problem supports the solution it motivates in `topic-solutionhood` (`basis: problem-solution`), because the writer offers the solution on the strength of the problem. In an adversative relation, the endorsed unit attacks the unit the writer concedes or rejects. A quoted counterclaim therefore appears as a conceded or rejected satellite that is attacked, never as a student assertion. This matches the PERSUADE hierarchy review, where relation type followed role.

Worked example (essay E0737CDC1E99): *[I favor of keeping the electoral college]* ← *[instead of changing to election by popular vote…]* `adversative-antithesis`, signal *instead of*; the same unit ← *[because it is fair.]* `explanation-justify`, signal *because*; *[A dispute over the outcome … is possible]* → *[but it's less likely than a dispute over the popular group.]* `adversative-concession`, signal *but*, satellite `conceded`; *[For example in 2012's election Obama recieved 61.7 percent…]* → that claim `explanation-evidence`, signal *For example*. `tests/test_graph_schema.py` encodes a shortened version as the reference fixture.

#### 4.4 Other records
- **Reference expectation:** ID, criterion, origin (`explicit_prompt`, `rubric`, `teacher_approved`, `source_passage`, `model_example`, or `generated_provisional`), and requirement status (`required`, `optional`, `illustrative`, or `unknown`).
- **Alignment:** student ID, reference ID, match type, evidence, and unresolved status. Separate “same topic” from “equivalent proposition”.
- **Finding:** type, student spans/node IDs, reference or criterion IDs, short evidence-based rationale, uncertainty, and review status.
- **Concept group, added later:** label, member IDs, summary, and links back to all supporting propositions. Permit membership in multiple groups and retain cross-group edges.

Keep author stance separate from rhetorical role: a counterargument may be quoted and rejected. Preserve contradictory claims as distinct proposition records even when their concept labels match. Source-independent generated material must never masquerade as an extracted fact.

## 5. Implementation order and completion checks

### Phase A — Data, schema, and baseline (roughly 2–3 focused days)

1. Define the common record and PERSUADE loader; obtain and validate the official training annotations, join them to the local essay records, select the electoral college assignment, and obtain its reference packet.
2. Save a deterministic sample and split manifest. Keep demographic fields out of model inputs; keep holistic scores for sampling and later analysis, not diagnosis prompts.
3. Implement spans and schema validation. Use released discourse roles and spans for two or three development paragraphs; manually supplement only finer proposition content, stance, qualifications, and relationships not covered by validated release annotations.
4. Scaffold a direct-LLM baseline using the same essay, references, criteria, and finding schema as the graph system. Check input/output contracts now; defer diagnostic optimisation and performance claims.

Complete when one example loads reproducibly, span offsets reproduce exact quotes, and baseline output validates. Passage acquisition may take longer than coding and is a dependency for factual assessment.

### Phase B — Flat graphs and verification (roughly 3–5 days)

1. Build and manually review a reference graph once per prompt/reference version. A model essay is illustrative, not an exhaustive answer key.
2. Extract student propositions and relations without showing the extractor the teacher graph or asking it to repair the essay. Preserve the essay's wording, uncertainty, attribution, and sequence.
3. Start with whole short essays; use paragraph chunks with neighbouring context only when needed. Retain stable global offsets and reconcile cross-paragraph relations.
4. Validate quotes, IDs, endpoints, and required fields in code. Use a separate verification pass for meaning, stance, polarity, edge direction, and missing assessment-relevant content.
5. Permit a bounded repair attempt, then retain unresolved flags. A faithfully extracted inaccurate claim must remain in the graph.
6. Evaluate predicted discourse units against the imported gold spans and roles. Review a small sample for annotation granularity and mapping errors; do not re-annotate existing role/span labels from scratch. Restrict new annotation to semantic fidelity and any edge information the release cannot support.

Complete when manually reviewed development examples preserve negation, qualifications, rejected counterarguments, and obvious inaccuracies. Every extracted claim and relationship must be traceable; failed extraction must not become a student diagnosis.

### Phase C — Alignment and diagnostic-path integration (roughly 3–5 days)

1. On tiny graphs, inspect all candidate pairs or use simple lexical candidates. Add semantic retrieval only when candidate volume warrants it. Any representation-alignment tuning requires annotated equivalence pairs and must remain separate from misconception decision thresholds.
2. Check candidate matches in context. Keep unmatched claims and valid novel arguments. Similarity does not imply agreement, and matching concepts does not justify merging opposing propositions.
3. Implement the finding schema and routing for these separate categories: `possible_misconception`, `unsupported_claim`, `insufficient_explanation`, `missing_required_content`, `internal_inconsistency`, `unclear_expression`, and `unresolved`. Record supported/valid alternatives as non-error decisions for evaluation.
4. Require verified extraction, student endorsement, and sufficient relevant evidence before issuing a possible-misconception finding. A disagreement with the reference graph is only a candidate for investigation.
5. Before declaring an omission, recheck the original essay and confirm that the criterion is actually required. Missing reference topics are not automatically missing required content.
6. Generate feedback only from recorded findings. A simple template is sufficient: passage, issue, supporting evidence/criterion, uncertainty, and revision suggestion.

Complete when one command produces every artifact for one essay and then a small batch, with human-readable evidence and both reference-availability paths exercised. At this stage, findings are integration outputs for review, not validated diagnoses. Do not optimise misconception sensitivity on PERSUADE or redefine unsupported claims as misconceptions. A useful prototype can conclude that evidence is insufficient.

### Phase D — Hierarchy and controlled comparison (roughly 3–4 days)

1. Group the existing propositions into broad concepts and add summaries with membership links. Within one essay, a model call in the style of `student_graph.py` returns each group as a summary plus a list of member unit IDs; code checks that the IDs exist, and the summary does not replace the units. A unit may belong to several groups. Group by topic (what a unit is about), not by support: the eRST primary tree already records what supports what, so a group may join units from different paragraphs, such as a counterclaim and its rebuttal. A group whose members differ in stance or polarity is labelled as containing a conflict, and its summary must state both sides.
2. Verify that summaries preserve qualifications and conflicting positions. Generate student groups independently of the reference organisation.
3. On PERSUADE, evaluate flat versus hierarchical representation fidelity, including information retention and summary distortion, using the same held-out pilot essays. Build hierarchy on the same verified flat graphs. Reserve the direct-LLM versus flat-graph versus hierarchical-graph diagnosis comparison for the later misconception evaluation, using comparable inputs, criteria, and model configuration.
4. Specify how hierarchy is used—for example, grouping candidate matches and retrieving member claims for judgement. The intended use is to match at the group level, then pass the member units and their primary-tree paths to the judge. Merely drawing grouped nodes does not test hierarchy's contribution.
5. After the main comparison, remove verification or discourse edges one at a time. Record model calls, tokens, latency, and cost as additional resources, since multi-stage conditions will differ.

Borrowed from HiRAG's indexing (HiIndex, reviewed 2026-09-26): summary nodes linked to their members, soft membership, and stopping when another layer no longer compresses the groups. Not borrowed: its entity nodes, which reduce "the Electoral College is fair" and "is not fair" to one entity and merge nodes by name; its undirected edges; summaries with no source link; random sampling of cluster members when a cluster is too long; and unseeded UMAP, which makes groups vary between runs. Embedding clustering (UMAP + Gaussian mixture with BIC) is unstable on the 20–60 units of one essay, so it is reserved for claims pooled across essays or against the reference graph, where it can supply Phase C candidate retrieval once candidate volume warrants it. Any clustering run fixes its random seeds and records them in the run configuration.

Complete when RQ1 results identify which representation stages preserve or distort information, even if hierarchy does not improve fidelity. This does not establish diagnostic performance.

### Phase E — Misconception data and diagnosis calibration (later milestone)

Proceed when a suitable dataset or expert-annotated collection includes genuine conceptual errors, evidence for their classification, and examples of valid claims, weak support, ambiguity, and other negatives. A new dataset name alone does not establish suitability. Load it through the common contract and establish separate development and test splits. Only then tune diagnosis prompts, thresholds, or decision rules; freeze the configuration before evaluating RQ2–RQ4. Retain the distinction between an endorsed inaccurate proposition and an unsupported or underdeveloped argument. Evaluate hierarchy and the direct-LLM baseline here without importing PERSUADE-based assumptions about misconception prevalence.

The duration estimates are a suggested work sequence, not a deadline commitment. Reference acquisition and expert annotation can proceed alongside coding.

## 6. How to use the papers

| Reading | Preliminary implementation | Defer |
|---|---|---|
| RST / eRST | Unit tiling, a single-rooted primary tree with nuclearity, a fixed GUM relation subset with definitions, signal-licensed secondary edges, and Parseval-style comparison (section 4) | The full 32-label inventory, token-level signal annotation for every relation, and parser training |
| INCEpTION | Design compatible span/relation annotations; use the platform if annotation volume warrants setup | Extensive annotation automation |
| KGGen | Compare a small extraction sample; borrow cautious equivalent-expression resolution | Aggressive clustering before checking stance and provenance |
| GraphJudge | Separate graph generation from a per-edge judge; one-to-one (Hungarian) soft matching only when graphs come from different texts | Its free-text entity triples; its judge criterion of agreement with model world knowledge, which would delete genuine student misconceptions (judge fidelity to the essay instead); its G-BLEU/G-ROUGE code as released, whose `split_to_edges` joins the characters of each triple's string form |
| DREsS | Keep content, organisation, and language assessment distinct | Treating essay-level scores as misconception gold labels |
| Topological Ordering for ARI | Optional dependency-subgraph diagnostic after relation extraction | Using topological order as an essay-quality score |
| HiRAG | Concept groups, summary-to-member links, soft membership, and retrieval of underlying detail (Phase D) | Full hierarchical RAG infrastructure; entity nodes merged by name; undirected edges; embedding clustering within a single essay |

These are proposed adaptations, not reproductions. KGGen's official examples expose entities and relation triples; inspect whether an adapter preserves the richer proposition metadata this project needs before adopting it as the extractor. See the official [KGGen repository](https://github.com/stair-lab/kg-gen), [GraphJudge repository](https://github.com/hhy-huang/GraphJudge), and [HiRAG repository](https://github.com/hhy-huang/HiRAG).

Topological ordering applies to an explicitly defined acyclic dependency subgraph. The full graph may include cycles and other edge types. Preserve sentence order independently and do not silently remove edges to force an ordering. Here ARI means argument relation identification.

The original RST PDF is scanned and yielded no extractable text; the RST guidance here is grounded in the report and readable eRST paper. The other supplied PDFs were text-extracted and their relevant descriptions reviewed.

## 7. Evaluation and debugging

For the PERSUADE RQ1 pilot, use released discourse spans and role labels as the primary gold data for segmentation and role evaluation. Manually supplement proposition fidelity, stance, negation, qualifications, optional equivalence pairs, and relations not covered by validated release fields. Do not use this pilot to calibrate misconception detection.

Report exact-boundary span precision/recall/F1 and a separately specified overlap-based measure with one-to-one matching. Report joint span-and-role F1 per role and macro-averaged, plus a role confusion matrix on matched spans. An optional role-classification run with gold boundaries must be labelled as an oracle segmentation experiment and kept separate from end-to-end extraction. Select overlap rules on development data and freeze them before the pilot check. Keep these RQ1 matching rules separate from later diagnosis matching rules.

For the later diagnosis phase, create an expert annotation table with essay ID, issue span(s), issue type, endorsement, evidence/criterion, rationale, and uncertainty. Record valid alternatives and no-issue cases too. For omissions, annotate the missing required criterion rather than inventing a student span. Human judgement remains necessary; model-generated labels are not independent gold labels.

Compare graphs according to what they share:

| Comparison | Method |
|---|---|
| Extracted graph vs PERSUADE gold (same essay) | Map units to gold elements by span overlap; report element-boundary crossings (units spanning two elements), role accuracy, and attachment accuracy of the element tree projected from the unit tree against the hierarchy candidates |
| Extracted vs human eRST-style annotation (pilot subset) | eRST/Parseval Span, Nuclearity (direction), Relation, and Full, reported separately for primary and secondary edges; signal precision/recall by type |
| Student graph vs reference graph (different texts) | One-to-one soft matching of units or edges (GraphJudge-style assignment), with a judge that checks each match against both texts; never exact-string metrics |

Evaluate three layers separately:

1. **Representation fidelity:** preservation of annotated propositions and relations; unsupported additions; polarity, attribution, and qualifier errors; source-link validity.
2. **Diagnosis:** issue-level precision/recall/F1 against expert labels. Fix matching rules beforehand—e.g. matching category plus token overlap of at least 0.5 intersection-over-union, with one-to-one matching; evaluate missing-content findings by criterion ID. Define or refine this matching rule on the later annotated misconception development set, never the held-out test set; keep it separate from model decision thresholds, report per-category counts, and track abstentions separately.
3. **Feedback:** expert ratings for correctness, specificity, evidence traceability, and usefulness of revision guidance, separately from diagnosis accuracy.

Use independent annotation on a shared subset where feasible, retain disagreements, and adjudicate. A 20-essay pilot supports debugging; final evaluation needs a larger annotated sample, sufficient examples per issue type, and preferably a held-out prompt to examine transfer.

Add small regression fixtures for negation, quoted/rejected claims, valid paraphrases, novel defensible arguments, conditional statements, genuine contradictions, and absent references. For example, a source stating “some vehicles can fail under condition X” does not contradict “vehicles usually work”; scope and quantifiers must survive extraction.

Persist prompt/schema versions, model identifier/settings, input hashes, raw responses, verification decisions, timing, usage, and failure reasons. Cache keys must include the stage and relevant configuration. Bound retries and log failures rather than substituting empty graphs as successful outputs.

## 8. First coding session

1. Create the common-record schema and PERSUADE loader for both essay and discourse-annotation files; validate joins and offsets, then select the fixed electoral-college sample. Add a second loader fixture to check the dataset boundary.
2. Load the released gold spans and roles for one development paragraph. Manually supplement only the additional semantic fields needed for its graph.
3. Implement student extraction to that schema and compare predicted discourse units with the released annotations, and proposition fidelity with the supplementary example.
4. Add exact-span and graph-reference validation.
5. Save the first inspectable `student_graph.json` and a list of observed extraction failures. Check that the titles-only record cannot supply factual reference evidence.

That gives a concrete first deliverable while reference acquisition and expert annotation are arranged.

## Implemented milestone

The standard-library implementation in `src/argument_graph/` now provides the common schema, validated JSON round trips, an allowlisted model-input projection, a PERSUADE adapter, auditable span recovery, hierarchy candidate preservation, and a deterministic score-band pilot selector. See `README.md` for commands and limitations.

The current electoral-college run is `data/processed/electoral_college_v6/` (records identical to v5; earlier run directories deleted): 1,818 essays; 19,561 recovered annotation rows out of 19,894; 333 unresolved (286 empty, 38 Unannotated fragments overlapping labelled spans, 8 ambiguous, 1 not found). 19,532 spans are confirmed within ±10 characters of their supplied offsets. Every emitted span was revalidated against unchanged essay text, and no two overlap. Essay IDs corrupted to scientific notation are replaced by text-hash IDs, and all essays join to the holistic file. The fixed pilot (10 development, 10 pilot-check essays) was unchanged from v2 to v5. In v6 (records identical to v5), E0737CDC1E99, which was used to design the argument-graph contract, moved to development and was replaced in pilot-check by C70EE5903373 from the same score band, giving 11 development and 10 pilot-check essays; `splits.json` records the change. Essays inspected during method design must never enter pilot-check. 23 regression tests pass. See `README.md` for the v1–v5 loader history.

Manual review (2026-09-25, on v4; sheets in `data/annotations/review_v4/`): a stratified sample of 101 spans found no location or boundary errors in labelled spans; the 12 errors were Unannotated word fragments, removed in v5. A sample of 30 hierarchy links showed an argument tree whose relation type follows the child's role; 2 were unclear. Verdicts were proposed by Claude and confirmed by the user, not blind-reviewed. Whether to import hierarchy links as `gold_relations` with role-derived types is an open decision, since it departs from the rule against inferring relations from roles. These counts describe mechanical import, not RQ1 model performance. Phase A is complete; next is the Phase B reference graph and flat-graph extraction on the development essays. Development gold graphs in the `argument_graph/0.1` format exist for four development essays (scores 1, 3, 3, 5) in `data/annotations/argument_graphs/`: written by Claude, reviewed and accepted without changes by the user on 2026-09-25. They are reviewed rather than independently annotated. They raised two schema questions. The four GUM labels they lacked (`mode-means`, `topic-solutionhood`, `topic-question`, `organization-phatic`) were added on 2026-09-26 and the affected gold edges relabelled (since confirmed); interrupted units now use eRST `same-unit` (rule 7 in 4.1; one case, E0737CDC1E99 u15), and problem → solution counts as derived support. Every later edit is listed in each file's `provenance.change_log` and was confirmed by the user on 2026-09-26, including the re-split of coordinated predicates to segmentation rule 2 in C0BA22AD7F2A, 656C7C849144 and 3165FA4998BC. Development extraction results for prompts v0.1–v0.3 are in the README; v0.3 is frozen for the pilot-check run. Pilot-check gold graphs for four pilot-check essays (scores 1, 3, 4, 6) are in `data/annotations/argument_graphs_pilot_check/`: Claude-written before any extraction of those essays, and accepted by the user without changes on 2026-09-26. The pilot-check run can therefore be scored on structure as well as on PERSUADE roles. v0.3 pilot-check results (2026-09-26, one run): exact unit F1 0.83, attachment 0.76, labelled 0.67, stance 0.82 (0.90 if source-attributed facts counted as endorsed), derived support/attack F1 0.66, root 3/4; PERSUADE role agreement 0.70 and element F1 0.62 over 10 essays. Development figures for the same prompt were 0.79, 0.80, 0.72, 0.97, 0.80, 3/4, 0.73 and 0.59. The pilot-check essays are now spent; a revised prompt needs a new held-out sample. Source passages obtained 2026-09-26 (`argument_graph.fetch_sources`; a second-hand copy of the Kaggle `train_prompts.csv`, SHA-256 pinned, not yet compared with the original), which moves the second reference condition from pending to available. Reference graphs for the three sources (Phase B step 1) and explicit-prompt expectations are drafted and await review. At the user's request, sources use their own format, `source_graph/0.1`, not the essay graph. The units have types (thesis, claim, fact, example, concession, opposing view, framing), and edges run from whole passages (supports, opposes, concedes, elaborates). Essay roles and the single-rooted tree had left most source units outside any reason. The graphs are gitignored with the copyrighted passages. The Python package was renamed from `ling_mapper` to `argument_graph` on 2026-09-26.
