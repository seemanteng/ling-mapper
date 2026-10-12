# RQ1 results: how faithfully do generated argument graphs match a human reading?

This section reports the first RQ1 results: four language models and two model-free baselines, each scored against the self-annotated reference graphs of 30 PERSUADE essays. Figures come from `data/runs/self30/comparison.md`, which `argument_graph.compare` regenerates. The reference set and its limits are described in [SELF_ANNOTATION.md](SELF_ANNOTATION.md).

## Summary

- Every model beats both baselines by a wide margin on attachment, labelled attachment, derived support/attack edges and role agreement. Each of these differences is confirmed by a paired bootstrap over essays. Finding the root is the exception (see Results).
- The four models are close on **where an essay's units attach** (0.53–0.57 of reference relations attach to the same head). On this measure the data cannot separate them.
- They differ more on **what the relation is called**, on **finding the thesis**, and on **minority stances**. Claude Sonnet 5.5 is best on the root (23/30) and labelled attachment (0.30). GPT `gpt-6.1-sol` is clearly best on the rare stances (Rejected F1 0.80, against 0.49–0.56).
- **Segmentation is the main gap.** The models split essays into more and smaller units than the reference (1,203–1,374 units against 859, except Claude at 950), and exact-span agreement is 0.44–0.63.
- **Labelled attachment is low for every model (0.19–0.30).** Most of the loss is between relation labels that the reference cannot tell apart (evidence versus justify, elaboration versus list or result), so the mapping onto the system's labels is part of the finding.
- **Ablations (Claude Sonnet 5.5):** the validator feedback loop is essential (only 11 of 30 essays are valid without it), removing the structure or segmentation rules lowers attachment by 0.07–0.12, and splitting extraction into two stages brings no measurable gain over one call. Giving the model the reference segmentation lifts attachment from 0.53 to 0.67, so segmentation explains about a third of the gap to a perfect score; the rest is in the relations.
- **Stance accuracy is a misleading headline.** 90% of reference units are Endorsed, so a baseline that predicts Endorsed everywhere scores 0.90. Per-class scores for Conceded, Rejected and Reported are the informative ones.

## Setup

### Reference
30 essays on one prompt ("Distance learning"), 5 per holistic score band 1–6, mean length 461 words (range 165–933). The author labelled all 30, then a guideline-consistency pass followed. The sheets were converted into `argument_graph/0.1` graphs: 859 units and 829 primary relations. The mapping from the author's labels onto the system's roles and eRST relations (SELF_ANNOTATION.md §6) restructures counterclaim/reply pairs and fronted contrasts so that the graphs satisfy the same validator as the model output. Polarity and relation signals were not annotated and are not scored.

### Systems
All four models used the same prompt (`student_graph/0.4`), two-stage procedure and output schemas. Stage 1 returns the units as exact quotes. Stage 2 returns roles, stances and the relation tree, which `validate_graph` checks. A failed check is sent back to the model, up to 3 attempts per stage, and a graph that never validates counts as a failure. Each model saw only the assignment and the essay.

| Model | Provider | Effort setting sent | Notes |
|---|---|---|---|
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Anthropic | `medium` (adaptive thinking) | |
| GPT (`gpt-6.1-sol`) | OpenAI | `reasoning_effort=medium` | |
| Gemini 3.1 Pro (`gemini-3.1-pro-preview`) | Google | thinking level `MEDIUM` | Preview model; Google may change it |
| Qwen 3.8 27B (`Qwen/Qwen3.8-27B:cerebras`) | Hugging Face router, hosted on Cerebras | `reasoning_effort=medium` | Open-weight (Apache-2.0) and much smaller than the other three |

"Medium" is each vendor's own setting, so the effort levels are matched by name, not by compute. Output tokens show how much each model actually thought (see Cost).

Two model-free baselines use the rule-based splitter that started the reference sheets:
- **majority:** the first unit is the root and position, and every other unit is endorsed evidence attached to the root as `explanation-justify`;
- **rules:** the root is the first unit with a thesis cue ("I think", "should"). Units before it are leads, units in the last paragraph are concluding summary, the rest are evidence. Units attach to the previous unit when they continue the sentence and to the root otherwise, and the relation label follows the connective.

### Metrics
`evaluate.py` maps each predicted unit to the reference unit it overlaps most, so a finer or coarser segmentation is not by itself counted as an attachment error.
- **Attachment:** share of reference relations whose predicted head is the same reference unit. **Labelled** adds the same relation label. **Class** adds the same coarse family (explanation, adversative, elaboration…).
- **Root:** the predicted root covers at least half of the reference root.
- **Role and stance agreement:** share of characters with the same label. Per-class precision, recall and F1 are character-level, pooled over essays.
- **Derived edges:** F1 of the support and attack edges derived from relation and stance.
- **Segmentation:** exact-span F1 (and boundary F1).
- An essay with no valid graph scores zero. Intervals are 95% percentile bootstraps over essays (2,000 resamples, same resamples for every system, so differences are paired).

## Results

### Headline

| Metric | Claude Sonnet 5.5 | GPT | Gemini 3.1 Pro | Qwen 3.8 27B | rules | majority |
|---|---|---|---|---|---|---|
| Root found | **0.77** (0.60–0.90) | 0.60 (0.43–0.77) | 0.60 (0.43–0.77) | 0.57 (0.40–0.77) | 0.40 | 0.30 |
| Attachment | 0.526 (0.45–0.59) | 0.534 (0.47–0.59) | **0.566** (0.51–0.62) | 0.539 (0.49–0.59) | 0.247 | 0.065 |
| Labelled attachment | **0.299** (0.25–0.35) | 0.193 (0.16–0.23) | 0.242 (0.20–0.29) | 0.240 (0.21–0.27) | 0.125 | 0.035 |
| Class attachment | **0.367** (0.31–0.42) | 0.276 (0.23–0.32) | 0.314 (0.26–0.37) | 0.329 (0.28–0.38) | 0.130 | 0.039 |
| Role agreement | **0.762** (0.70–0.82) | 0.728 (0.68–0.78) | 0.716 (0.65–0.78) | 0.692 (0.63–0.75) | 0.590 | 0.568 |
| Stance agreement | 0.946 | **0.947** | 0.931 | 0.935 | 0.902 | 0.902 |
| Derived edges F1 | **0.467** (0.39–0.55) | 0.408 (0.36–0.46) | 0.459 (0.40–0.53) | 0.414 (0.36–0.47) | 0.087 | 0.052 |
| Segmentation F1 (exact) | **0.628** (0.55–0.69) | 0.442 (0.38–0.50) | 0.491 (0.43–0.55) | 0.533 (0.47–0.60) | 0.893\* | 0.893\* |
| Segmentation F1 (boundary) | **0.836** | 0.746 | 0.772 | 0.794 | n/a | n/a |

\*Not evidence of quality: the baselines use the splitter that produced the reference sheets.

**Models against baselines.** Every paired difference between a model and either baseline excludes zero for attachment, labelled attachment, role agreement and derived edges (for example Qwen minus rules: attachment +0.29, labelled +0.12). Root finding separates Claude from the baselines (+0.37 over rules) but not the other three models from the rules baseline (interval includes zero).

**Models against each other.** Claude's lead on the root is +0.17 over GPT and Gemini and +0.20 over Qwen (all intervals exclude zero), and its lead on labelled attachment is +0.06 to +0.11 (also excluded zero). Attachment does not separate any pair of models (every interval includes zero), and neither does derived-edge F1. Gemini's higher attachment (0.566) is within noise. Among the three non-Claude models, the only difference that excludes zero is labelled attachment, where Gemini is ahead of GPT by +0.05. Qwen against GPT on the same metric is borderline (+0.05, interval −0.09 to 0.00 for GPT minus Qwen).

### Roles

Macro-F1: Claude 0.68, GPT 0.67, Gemini 0.66, Qwen 0.64; rules 0.30, majority 0.13.

| Role (reference units) | Claude | GPT | Gemini | Qwen |
|---|---|---|---|---|
| Concluding summary (96) | 0.91 | 0.86 | 0.86 | 0.83 |
| Lead (72) | 0.90 | 0.90 | 0.91 | 0.87 |
| Evidence (504) | 0.86 | 0.81 | 0.81 | 0.76 |
| Position (30) | 0.77 | 0.75 | 0.80 | 0.78 |
| Counterclaim (32) | 0.75 | 0.71 | 0.63 | 0.70 |
| Rebuttal (24) | 0.65 | 0.54 | 0.52 | 0.48 |
| Claim (96) | 0.53 | 0.49 | 0.52 | 0.46 |

Lead and concluding summary are easy for all four, because the essay's position in the text gives them away. **Claim is the weak role for every model (F1 about 0.5)**: the models mix up a paragraph's general reason (claim) with its specifics (evidence), which is the distinction the annotator settled by rule after the consistency pass. Rebuttal is also weak, and recall (0.66–0.84) is higher than precision (0.35–0.53), so models call too many units rebuttals. The five "Other" units (unannotated) are too few to judge.

### Stance

| Stance (reference units) | Claude | GPT | Gemini | Qwen | Baselines |
|---|---|---|---|---|---|
| Endorsed (771) | 0.98 | 0.98 | 0.97 | 0.98 | 0.95 |
| Conceded (59) | 0.70 | 0.71 | 0.61 | 0.66 | 0.00 |
| Rejected (21) | 0.49 | **0.80** | 0.50 | 0.56 | 0.00 |
| Reported (8) | 0.39 | **0.54** | 0.37 | 0.50 | 0.00 |
| Macro-F1 | 0.640 | **0.757** | 0.615 | 0.672 | 0.237 |

Models rarely mislabel an Endorsed unit, but they miss the minority stances. For Rejected, Claude and Gemini find only 36% and 48% of the reference units (precision is higher, 0.77 and 0.52), and Qwen finds 42%. GPT finds 74%. Rejected and Reported have only 21 and 8 reference units, so these rows indicate a direction and carry no firm ranking.

### Segmentation and validity
The models over-segment: Claude produced 950 units against the reference's 859, Qwen 1,203, Gemini 1,294 and GPT 1,374. Exact-span F1 is 0.44–0.63, and boundary F1 is higher (0.75–0.84), which shows most boundaries are close but spans differ. Because the reference started from a rule-based splitter and was only corrected for clear errors, these scores measure agreement with that splitter, not with free human segmentation.

All four models produced a valid graph for all 30 essays within the retry budget, but few passed on the first attempt (two attempts means both stages valid first time):

| | Both stages valid first time | Needed retries | Failed |
|---|---|---|---|
| Claude Sonnet 5.5 | 14/30 | 16/30 (2 essays took 4 attempts) | 0 (see note) |
| GPT | 12/30 | 18/30 | 0 |
| Gemini | 6/30 | 24/30 | 0 |
| Qwen | 6/30 | 24/30 | 0 |

Note: Claude failed essay 1 on its first full run (segmentation: the model quoted the text with the student's typos corrected, so the quotes were not exact). It was run again once and then passed. Report it as "29/30 on the first run, 30/30 after one retry". The validators matter: without the feedback loop, the first-attempt validity rates above would have been the failure rates.

### Results by essay score band

Attachment accuracy by PERSUADE holistic score (5 essays per band, so each cell has few relations; trends only):

| Score | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Claude | 0.38 | 0.44 | 0.50 | 0.44 | 0.61 | 0.63 |
| GPT | 0.45 | 0.52 | 0.54 | 0.54 | 0.58 | 0.53 |
| Gemini | 0.53 | 0.49 | 0.61 | 0.53 | 0.61 | 0.57 |
| Qwen | 0.53 | 0.42 | 0.57 | 0.53 | 0.61 | 0.51 |

Claude's accuracy rises with essay quality (0.38 to 0.63), which is the pattern one would expect if weaker essays are harder to structure. The other models show no clear trend.

### Where the labels disagree
Among relations that attach to the correct head, the commonest label errors are the same across models:
- the reference `explanation-evidence` predicted as `explanation-justify` (30–44 cases) and the reverse (17–24);
- `elaboration-additional` predicted as `joint-list` (14–22) or, for GPT and Gemini, as `causal-result` (26–30), and `explanation-evidence` as `causal-cause` (27–28).

The first pair is a mapping artefact. The annotator had one label ("backs it up") for two relations that the system distinguishes, and the converter assigns them by the target's role. Class-level attachment (0.28–0.37) is therefore the fairer measure of relation quality, and it still leaves a large gap.

### Cost
| | Input tokens | Output tokens |
|---|---|---|
| Claude Sonnet 5.5 | 0.49M | 0.15M |
| GPT | 0.33M | 0.21M |
| Gemini | 0.46M | 0.47M |
| Qwen 27B | 0.44M | 1.08M |

Output tokens include reasoning. Qwen thinks about seven times as much as Claude to reach similar attachment. Prices were not recorded. Add them from each provider's invoice before reporting cost.

## Ablations: which parts of the pipeline matter

All ablations use Claude Sonnet 5.5 at `medium` effort on the same 30 essays and change one thing from the default (the run reported above: two stages, validator feedback with up to 3 attempts per stage, full prompt). An essay with no valid graph scores zero. Intervals are the same paired bootstrap as above; the figures are in `data/runs/ablation/ablation.md`.

| Run | What changes | Valid essays | Root | Attachment | Labelled | Role agr. | Derived F1 | Tokens in / out |
|---|---|---|---|---|---|---|---|---|
| **default** | none | 30 | 0.77 | 0.526 | 0.299 | 0.762 | 0.467 | 492k / 146k |
| no-retry | one attempt per stage | **11** | **0.27** | **0.170** | **0.089** | **0.269** | 0.444 | 317k / 91k |
| one-stage | units and relations in one call | 30 | 0.67 | 0.520 | 0.292 | 0.751 | 0.474 | 324k / 169k |
| no segmentation rules | rule block removed | 30 | 0.83 | **0.411** | 0.251 | 0.757 | **0.363** | 432k / 117k |
| no role rules | rule block removed | 29 | 0.73 | 0.493 | 0.271 | **0.696** | **0.413** | 481k / 153k |
| no structure rules | rule block removed | 28 | 0.70 | **0.460** | **0.221** | 0.693 | **0.346** | 520k / 178k |
| effort low | reasoning effort | 30 | 0.77 | 0.514 | 0.291 | 0.776 | 0.439 | 498k / 143k |
| oracle segments | reference segmentation given, Stage 1 skipped | 30 | **0.90** | **0.673** | **0.363** | **0.803** | **0.540** | 378k / 122k |

Bold marks a paired difference from the default whose 95% interval excludes zero (in the direction shown).

1. **The validator feedback loop is what makes the pipeline usable.** With one attempt per stage only 11 of 30 essays produce a valid graph (19 fail the checks), and the score over all 30 collapses (attachment 0.17). On the essays that do pass, the quality is not measured here, since the comparison counts failures as zero. The default needed on average 2.6 attempts per essay where 2.0 would mean no retries.
2. **Splitting segmentation from relation-building makes no measurable difference.** The one-stage run matches the default on every metric (all intervals include zero) and uses about a third fewer input tokens (324k against 492k), though more output tokens. It is the cheaper design, and nothing in these data supports the two-stage split on quality grounds.
3. **The prompt's rule blocks matter, unevenly.**
   - Removing the **structure rules** costs attachment (−0.07), labelled attachment (−0.08) and derived edges (−0.12), and makes the model need more retries (3.1 attempts per essay against 2.6) and fail 2 essays.
   - Removing the **segmentation rules** costs attachment (−0.12) and derived edges (−0.10), yet exact-span segmentation F1 is unchanged (0.64 against 0.63). The rules do not change where most units are cut; they change which units the model ends up with in a way that matters for the relations. These data do not say why.
   - Removing the **role rules** costs role agreement (−0.07) and a smaller, borderline amount of derived-edge F1 (−0.05). Attachment and labelled attachment do not change measurably, which is the effect one would expect.
4. **Reasoning effort has no visible effect here.** Low and medium effort give the same scores, and Sonnet used almost the same number of tokens in both (143k and 146k output). A third run at high effort was stopped after 13 of 30 essays to save cost and is not reported.
5. **Segmentation explains part of the gap, not most of it.** Giving the model the reference segmentation (a diagnostic, not a version of the system) raises attachment from 0.53 to 0.67, labelled attachment from 0.30 to 0.36, and finds the root in 27 of 30 essays (from 23). Even with perfect units, a third of the reference attachments are missed and labelled attachment stays near 0.36, so the remaining loss is in choosing the heads and relations.

Caveats specific to the ablations: they use one model and one run each; "valid essays" is read from the same run so a fair comparison of the quality of valid graphs would need a larger set; the per-class stance rows move a lot between runs (Reported has 8 reference units) and are not interpreted here; and the three rule-removal runs change the prompt for both stages, including wording in the user message ("following the segmentation rules" is dropped when that block is removed).

## Interpretation for RQ1

1. **The graphs are far from random and well above simple rules.** The models recover the main structure (thesis, introduction and conclusion, evidence under claims) but do so imperfectly: roughly half of the reference attachments are reproduced, and about a quarter to a third carry the same relation family.
2. **The system is more reliable at the essay's skeleton than at fine rhetorical distinctions.** Claim versus evidence, evidence versus justify, and rebuttal precision are where models and human reading diverge.
3. **The rare stances are the open problem.** For RQ2, which relies on identifying conceded and rejected views, most models miss over half of the Rejected units. The result suggests a stance-specific prompt or check before relying on the graphs for misconception detection.
4. **The pipeline's design choices are worth keeping selectively.** The validators and the structure rules earn their place. The two-stage split does not, on this evidence. Higher reasoning effort is not needed.
5. **Choosing a model is a trade-off, not a ranking.** Claude is best on root and relation labels, GPT on rare stances, and an open 27B model is competitive on attachment at a much higher token cost.

## Threats to validity

- **Single annotator, and the annotator designed the system.** There is no inter-annotator agreement yet. The planned self-agreement re-label and a small second-annotator check will bound the reference noise. Until then the scores say how close the models come to one person's reading, not to a settled truth.
- **Claude reviewed the reference.** During the consistency pass Claude Opus 5.5 suggested corrections, and the author accepted or rejected each. This may favour Claude's reading of the guidelines; the Claude row should be read with that in mind.
- **The mapping is a modelling choice.** Splitting "backs it up" into justify and evidence by target role, flipping counterclaim/reply pairs, and the eight "other" relations mapped to elaboration all affect labelled scores. They are documented in SELF_ANNOTATION.md §6.
- **Segmentation is not independent of the baseline splitter** (see above), and unit counts differ across models.
- **One prompt and 30 essays.** The intervals show variation over these essays only. Nothing here says how the models behave on other topics. A second-prompt set (`cell_phones_v1` exists) is the planned check.
- **Single run per model.** Each model was run once, with no repeats, so run-to-run variation is not measured. One Claude essay needed a rerun.
- **Settings are matched by name.** The "medium" setting is each vendor's, and the models differ in size (Qwen 27B against flagship models). Gemini 3.1 Pro is a preview model.
- **Polarity and signals were not annotated.** The results say nothing about negation or about relation signals.
- **The prompt was developed on a different topic** (Electoral College essays), so none of the 30 essays was used for tuning. It was not tuned for the other three vendors, and a prompt tuned per model could move their numbers.

## Reproducing

```sh
# reference graphs from the sheets
PYTHONPATH=src python3 -m argument_graph.reference_graph
# one model run (resumable); repeat per model
PYTHONPATH=src .venv/bin/python -m argument_graph.student_graph \
  --records data/processed/distance_learning_v3/records.jsonl \
  --splits data/processed/distance_learning_v3/splits.json \
  --essay persuade:<ID> ... --output-dir data/runs/self30 \
  --provider anthropic --model claude-sonnet-5-5 --effort medium --keep-model-failures
# baselines, scoring, comparison
PYTHONPATH=src python3 -m argument_graph.baselines --records data/processed/distance_learning_v3/records.jsonl --output-dir data/runs/self30
PYTHONPATH=src python3 -m argument_graph.evaluate --run-dir <run> --records data/processed/distance_learning_v3/records.jsonl \
  --gold-dir data/annotations/self_annotation_online_learning_30/reference_graphs
PYTHONPATH=src python3 -m argument_graph.compare --records ... --gold-dir ... --run NAME=DIR ... --output data/runs/self30/comparison.md
```

Provider keys are read from `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `HF_TOKEN`). Run folders under `data/runs/` are git-ignored, so keep a copy of `comparison.md` and each run's `metrics.json` and `manifest.json` with the report.
