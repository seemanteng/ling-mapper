# Student graph extraction: prompt versions and results

History of the extraction prompt (`PROMPT_VERSION` in `src/argument_graph/student_graph.py`) and every scored run, oldest first. All runs use Claude Opus 5 at effort `high`, one run per version, scored against Claude-written, user-reviewed gold graphs (4 development and 4 pilot-check essays). The current summary is in the README.

## Extraction details

`student_graph.py` produces `argument_graph/0.1` graphs in two validated stages. **Segment:** the model returns units as exact quotes, and code locates them in the unchanged essay and checks that they tile it. **Relate:** the model returns roles, stances, the primary tree, secondary edges and signal quotes, and code locates the signals and runs `validate_graph`. A quote is located exactly if possible; failing that, a whitespace run in the quote may match any whitespace run in the essay, because the model cannot reproduce characters such as non-breaking spaces. The stored unit or signal is always the essay's own slice. This fallback was added after two pilot-check essays failed on `\xa0` (2026-09-26); it leaves every earlier successful segmentation unchanged. Failed checks are sent back verbatim for up to `--max-attempts` attempts (default 3); a graph that never validates is logged as a failure, never repaired or saved as empty. The model receives only `model_input()` (assignment and essay text), and the system prompt is generated from `graph_schema.py`. It contains no gold graphs, but from v0.2 its rules quote short phrases from development essays as examples, so development scores are optimistic. It defaults to Claude Opus 5 (`claude-opus-5`) with adaptive thinking, effort `high`, structured JSON output, and server-side refusal fallback. It runs the development split by default and refuses pilot-check essays unless `--allow-pilot-check` is given.

Pilot-check essays are written to the same run folder as the development essays of that configuration, so report them separately (from `per_essay` in `metrics.json`). Score the pilot-check gold graphs with `--gold-dir data/annotations/argument_graphs_pilot_check`; the gold-graph summary then covers only those four essays, while the PERSUADE summary still covers every essay in the folder. Changing the prompt after seeing pilot-check scores makes them development data.

Each run directory is keyed by prompt version, model, effort and a hash of the prompt and schemas. It holds `system_prompt.txt`, `manifest.json` (config, records hash, per-essay status and token usage), and per essay `<id>.graph.json` plus `<id>.log.json` (every attempt's output, errors, stop reason, usage and request ID). Essays already extracted under the same configuration are skipped unless `--force` is given.

## v0.1–v0.3 on the development essays

Claude Opus 5, effort `high`, one run per prompt version on the 11 development essays (4 with gold graphs). Every version extracted all 11 essays. v0.1 is scored against the gold graphs as re-split for v0.2, so all three rows use the same gold.

| Prompt | Exact unit F1 | Boundary F1 | Root | Attachment | Labelled | Role | Stance | Derived F1 | PERSUADE role | PERSUADE element F1 | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.1 | 0.79 | 0.92 | 2/4 | 0.66 | 0.53 | 0.54 | 0.85 | 0.48 | 0.62 | 0.49 | $4.19 |
| 0.2 | 0.78 | 0.91 | 3/4 | 0.72 | 0.63 | 0.79 | 0.91 | 0.59 | 0.76 | 0.62 | $4.04 |
| 0.3 | 0.79 | 0.91 | 3/4 | 0.80 | 0.72 | 0.71 | 0.97 | 0.80 | 0.73 | 0.59 | $4.66 |

v0.2 added PERSUADE-style role rules, label tests for justify versus cause and for joint-list, and splitting of predicates that share a subject. v0.3 revised only the claim and counterclaim rules. The claim/evidence boundary remains the main role error, and it moved between versions rather than shrinking. v0.1 labelled too much as claim, v0.2 too much as evidence, and v0.3 too much as claim again. Roles do not enter derived support/attack edges, which come from relations and stance, so v0.3 was frozen for its structure scores. These numbers come from essays used to tune the prompt, against gold that Claude wrote and the user reviewed. Each is a single run with no measure of run-to-run variance.

## v0.3 on the pilot-check essays

One run of v0.3 on the 10 pilot-check essays, which had not been used for tuning, scored 2026-09-26 against the four pilot-check gold graphs and against PERSUADE. All 10 were extracted (cost $4.93, plus about $0.40 for two essays that failed before the whitespace fix and were re-run). Development figures for the same run are shown for comparison.

| Split | Exact unit F1 | Boundary F1 | Root | Attachment | Labelled | Stance | Derived F1 | PERSUADE role | PERSUADE element F1 |
|---|---|---|---|---|---|---|---|---|---|
| Development (4 gold / 11 essays) | 0.79 | 0.91 | 3/4 | 0.80 | 0.72 | 0.97 | 0.80 | 0.73 | 0.59 |
| Pilot-check (4 gold / 10 essays) | 0.83 | 0.94 | 3/4 | 0.76 | 0.67 | 0.82 | 0.66 | 0.70 | 0.62 |

Most of the stance gap comes from facts the writer attributes to a source ("According to Source 2, …", "as seen in the article, …"). The model marks them `reported`, following the prompt's definition ("attributed to others"). The gold marks them `endorsed`, because the writer uses them as their own evidence. Counting `reported` as `endorsed` raises pooled stance agreement from 0.83 to 0.90 and leaves derived edges unchanged. The user has since decided on `endorsed` for such facts (plan section 4.1); the next prompt version must say so. The drop in derived F1 is structural: explanation-justify was labelled causal-cause or causal-result five times, a confusion v0.2 had removed on the development essays. The root miss (671D0569C835) is the root-choice ambiguity noted for the pilot-check gold. The pilot-check essays have now been used. Any later prompt change needs a new held-out sample drawn from the remaining electoral-college essays.

## v0.4 (2026-09-27)

A review of the graph for one real essay (a web run, not a PERSUADE essay) found errors that the scores had not surfaced. They were checked against the graph and fixed in `student_graph/0.4`:
- **Concession scope.** Only the first unit of a conceded passage could be `conceded`, because the validator required every conceded unit to be in an adversative relation; the rest were pushed to `reported`. The validator now accepts a conceded or rejected passage: units linked by primary edges, with the same stance, to a unit in an adversative relation. The prompt says every unit of a conceded passage is conceded.
- **"Instead of" is not rejection.** "Instead of hiring local artists, they used AI" describes what someone else chose; it is `adversative-contrast`, and the alternative is not `rejected` by the writer.
- **Therefore/so/thus mark an inference.** When they introduce the writer's conclusion, the relation is `explanation-justify`, not `causal-result`. Causal labels are for events in the world.
- **Restatement means the same claim, with the same strength.** A stronger conclusion or a generalisation ("too many students" becoming "students have surrendered all their learning") gets its own relation, so the change stays visible.
- **Polarity is defined.** It is negative only when the unit's main claim is negated, not when a phrase inside it is.
- **The stance decision.** A fact the writer cites from a source and uses as evidence is `endorsed`.

Six units in the gold graphs were updated to the conceded-passage convention, logged in each file's `change_log`: 671D0569C835 x33b, E0737CDC1E99 u9, F3B4F60CE90C w17 and w35, 656C7C849144 c19, and C70EE5903373 v19. The other candidates were checked and are correct as annotated. The prompt's new examples come from the reviewed essay, so that essay no longer tests v0.4 fairly. **v0.4 scores** (one run each, 2026-09-27; all 21 essays extracted, about $10.60 including one essay re-run after an API time-out). Both versions are scored against the updated gold.

| | Exact unit F1 | Root | Attachment | Labelled | Stance | Derived F1 | PERSUADE role | PERSUADE element F1 |
|---|---|---|---|---|---|---|---|---|
| Development, v0.3 | 0.79 | 3/4 | 0.80 | 0.72 | 0.96 | 0.77 | 0.73 | 0.59 |
| Development, v0.4 | 0.81 | 3/4 | 0.80 | 0.66 | 0.97 | 0.73 | 0.73 | 0.57 |
| Pilot-check, v0.3 | 0.83 | 3/4 | 0.76 | 0.67 | 0.80 | 0.64 | 0.70 | 0.62 |
| Pilot-check, v0.4 | 0.91 | 3/4 | 0.72 | 0.67 | 0.94 | 0.66 | 0.69 | 0.55 |

Stance on pilot-check improves most, from 0.80 to 0.94, largely because source-cited facts are now `endorsed`, as in the gold. Segmentation improves on both sets. Attachment and labelled accuracy move in both directions by amounts within the noise of one run on 4 essays. Across both sets, label errors on correctly attached units fall from 25 to 23, justify read as causal falls from 5 to 2, and "therefore/thus/hence" labelled as causal appears once in 21 essays. PERSUADE element F1 drops slightly, from 0.62 to 0.55 on pilot-check. The pilot-check essays have now been used twice, so these are comparisons, not held-out estimates. v0.4 is kept.

The graph viewer (and the browser page) has a third view, **Propositions** (`graph_schema.propositions`). It joins each unit with its reporting frame, its conditions and its split-off parts ("Critics may argue" + "that technology leads to social good…"), and keeps the relations between propositions. It is derived from the graph, which is unchanged. For the reviewed essay, 81 units become 75 propositions. Grouping units into concepts across the essay (the review's "conceptual layer") is the Phase D work and is out of the current scope.
