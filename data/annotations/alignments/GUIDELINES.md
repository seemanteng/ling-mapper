# Alignment guidelines (align/0.2)

Each unit of a student graph gets one label and, where the label needs it, the source units it draws on. The judge prompt in `src/argument_graph/align.py` states the same rules.

| Label | Use when | Source units |
|---|---|---|
| `quote` | The unit copies the source's wording (spelling slips and small changes allowed). | Required |
| `paraphrase` | The unit states the same proposition as the source unit(s) in other words, without changing its meaning. | Required |
| `distorted` | The unit is based on specific source unit(s) but changes the meaning (see R2 and R3). | Required, plus a note saying what changed |
| `related` | The unit uses specific source content to assert something the source does not say (see R1). | The units whose content is used |
| `none` | The unit has no basis in the sources. | None |

## Rules added on 2026-09-26 after the first judge run

- **R1. `related` needs specific content.** The unit must use a particular fact, number, example or named argument from a source. A stance, evaluation or call to action that only agrees with a source's position is `none`. This covers "we should abolish the Electoral College" and "the system is unfair", even when a source says the same in general terms. Using a source's wording for the student's own thesis does not make it `related`.
- **R2. Overstatement is distortion.** A unit that restates a specific source claim but strengthens it is `distorted`. Examples: *possible* becomes *bound to happen*, *more attention* becomes *the only ones*, *most popular votes* becomes *a majority*, *appeal across regions* becomes *must win in all regions*.
- **R3. Contradiction is distortion.** A unit that asserts something a source unit contradicts is `distorted`, even when it does not reword that unit. This also covers presenting a view the author reports only to rebut, extended beyond what the source says, as established fact. Example: "the Electoral College does not [give] many voters the passion to vote", where Posner reports that it "may turn off" voters in safe states, in order to rebut it.

Clarifications made while applying R1–R3:
- R3 does not apply when another source supports the claim. A student siding with one source is not distorting the other; for example, "electors vote what the state wants" is supported by Posner (electors are trusted, and that trust is rarely betrayed).
- Dropping a qualifier the author concedes, as in "not democratic" for Posner's "not democratic in a modern sense", is not R2 overstatement.
- A verbatim copy of a source's evaluation stays `quote`. R1 is about `related`, not about copied wording.

Other rules (from `align/0.1`): label a unit by what it asserts, even when it repeats an earlier point; a citation is evidence about which unit is meant but must be checked; list every source unit a compressed unit draws on, and no more.

## Gold revision log

The gold was first written before any judge run. It was then revised on 2026-09-26 by applying R1–R3 to every `related` and `paraphrase` unit and to every `none` unit that restates a source position. The revision was done after seeing the first judge run, so each change is recorded in the file's `provenance.change_log` with the rule that caused it, for the user's review. Scores on these 8 essays are therefore development figures. A fair estimate needs gold for essays neither the judge prompt nor the annotator has been tuned on.
