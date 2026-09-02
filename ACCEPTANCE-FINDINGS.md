# Task 13 — the acceptance check, and what it actually showed

Measured 2 Sep 2026 on `projects/Before_Adam_The_Story_of_Iblis` — 347 lines, 18.1 minutes,
live Gemini, `gemini-2.5-flash`. This task produces evidence, not code.

## The short version

**The number of pictures decides whether a picture has anything to photograph. Where the
boundaries fall barely matters.** At 60 pictures, 78% of them land on narration with fewer
than two photographable things in it, and no method of cutting fixes that. At 15 pictures,
13% do.

The owner's instinct — cutting his film from 60 pictures to 15 — was the fix. The model
route helps at the margin and is worth keeping for the descriptions it writes, but it is
not what moved this number.

## Task 13's own metric does not work

The plan's pass condition was "spans with almost nothing to photograph drops well below 18".
Measured at 60 pictures:

| method | empty spans (Task 13 metric) |
|---|---|
| clock cut (`plan_image_budget`) | 11 of 60 — deterministic |
| model-chosen | 10, 11, 12, 16 over four runs — mean 12.2, stdev 2.6 |
| **random partition** | **mean 8.8** over 400 trials |

A partition made by throwing darts scores better than either real method. The metric counts
a span as empty only when it has ≤1 concrete word **and** contains an abstract phrase, and
only 33 of 347 lines carry an abstract phrase — so a short span almost never qualifies. The
metric rewards cutting small, which is the opposite of what the project set out to do.

It cannot be used to decide anything, and the 18-of-60 baseline it cites does not reproduce:
running the real `plan_image_budget` at 60 gives 11, not 18.

## A measure that length cannot flatter

Count, for each picture, how many photographable things its whole stretch of narration
names. A picture with fewer than two is *starved* — there is nothing in it to picture.
Compared at the same picture count, so no method is flattered by cutting smaller:

| method (60 pictures) | starved | median concrete words | worst |
|---|---|---|---|
| clock cut | 47 of 60 | 0.5 | 0 |
| random partition | 45.3 | 0.0 | 0.0 |
| model-chosen | 43, 43, 44 | 0.0 | 0 |

The model is slightly ahead of both, and all three sit in the same band. At 60 pictures this
film does not have the material, however it is cut.

## What actually moves it

Clock cut at every count, so the shape is not a model artefact:

| pictures | average hold | starved | starved % | median concrete words |
|---|---|---|---|---|
| 10 | 108.7s | 1 | **10%** | 5.5 |
| 15 | 72.5s | 2 | **13%** | 3.0 |
| 20 | 54.4s | 6 | 30% | 2.0 |
| 30 | 36.2s | 16 | 53% | 1.0 |
| 40 | 27.2s | 26 | 65% | 1.0 |
| 60 | 18.1s | 47 | **78%** | 0.5 |
| 90 | 12.1s | 76 | 84% | 0.0 |

The relationship is monotonic and steep between 15 and 40. For this script the usable range
is roughly **10 to 20 pictures**, and above 30 most pictures are illustrating narration that
names nothing.

The plan asserted that "success is the empty-span count falling, NOT a lower picture count",
and that judging on count would let a worse film pass. On this script that is backwards: the
empty-span count is overwhelmingly a function of picture count.

## What the model route is still worth

Not this metric — the descriptions. Measured the same day:

- every picture comes back with a written description of the whole stretch it carries
  (60 of 60, twice), where the clock cut supplies boundaries and no words at all
- blank descriptions on the owner's real export: 27 of 30 → 0
- project brief riding on every prompt: 19 of 19 → 0
- negations, which text encoders cannot parse: 15 of 15 → 0

Those are the fixes that changed what he can generate. The boundary placement is a smaller,
real, second-order gain.

## Caveats, stated plainly

- "Photographable" is a fixed list of about thirty nouns and verbs, inherited from the plan.
  It is a proxy. The **absolute** percentages depend on that vocabulary; the **shape** of the
  curve does not, because any fixed vocabulary spreads the same way across more or fewer
  buckets.
- The model answers the same request differently between runs — 10 to 16 empty spans on
  identical input. Any single run is not evidence. Four runs give stdev 2.6, so differences
  smaller than about 5 spans are noise.
- Narration seconds here are the word-count estimate; this film has 0 of 347 lines measured.
  Measuring would move the holds, not the concrete-word counts.

## What this suggests doing

1. Plan in **Auto**, and treat a proposal above ~20 pictures on a script like this as a
   signal that the narration, not the planner, is the constraint.
2. Keep the model route for the descriptions.
3. Replace Task 13's metric with the starved count above if this is ever measured again.
