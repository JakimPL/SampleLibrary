# What the two descriptors actually do

Measured on 2026-09-09 with `samplecloud-evaluate`, over the full catalog of 127,588 samples, seed 0.
Both baselines hold a vector for every sample: `invariant` (experiment 2, 192 dimensions) and
`librosa` (experiment 3, 65 dimensions).

The harness's own label counts reproduce the figures in
[`09-measurements.md`](09-measurements.md) exactly -- 13,373 keyword-labeled samples and 124,420
reached by note events -- which is the join checking itself.

## The two descriptors answer different questions

| | `invariant` | `librosa` |
|---|---|---|
| Transposition rank-1 | **62.9%** | 14.3% |
| Transposition median rank | **1** | 1,530 |
| Category accuracy | 0.472 | **0.564** |
| Category macro-F1 | 0.337 | **0.468** |
| Note agreement, pitch count | +0.520 | **+0.567** |
| Note agreement, span | +0.432 | **+0.492** |
| Single-pitch AUC | 0.730 | **0.768** |

Each descriptor wins the half it was built for and loses the other. `invariant` earns its pitch
invariance by discarding pitch, and the same discarding costs it the timbral detail a category or a
playing style is read from. `librosa` describes timbre well and moves under a retuning.

**Neither descriptor does both, which is the case for one learned space that does.** A codec adopted
on reconstruction alone would repeat this trade rather than resolve it, which is why
beating both is a condition of adopting a learned codec.

## Transposition retrieval, offset by offset

Sixty probes, each retuned across the whole grid and searched against all 127,588 samples.

| Offset | `invariant` rank-1 | `invariant` median rank | `librosa` rank-1 | `librosa` median rank |
|---|---|---|---|---|
| -24 st | 51.7% | 1 | 0.0% | 23,473 |
| -17 st | 58.3% | 1 | 0.0% | 12,687 |
| -12 st | 75.0% | 1 | 0.0% | 2,993 |
| -7 st | 75.0% | 1 | 0.0% | 1,224 |
| -5 st | 70.0% | 1 | 1.7% | 284 |
| -2 st | 80.0% | 1 | 78.3% | 1 |
| +2 st | 81.7% | 1 | 75.0% | 1 |
| +5 st | 70.0% | 1 | 11.7% | 66 |
| +7 st | 68.3% | 1 | 3.3% | 494 |
| +12 st | 56.7% | 1 | 1.7% | 1,837 |
| +17 st | 45.0% | 2 | 0.0% | 5,311 |
| +24 st | 23.3% | 74 | 0.0% | 14,400 |

`librosa` holds only within a whole tone and falls away sharply from there. `invariant` degrades
gently and still finds one retuning in four two octaves out.

The median rank is what separates the two most sharply. `librosa` at -24 st puts the original
23,473rd out of 127,588 -- not merely outside the top few, but nowhere near the sample it came from.

## Where the categories are easy and hard

Per category, sorted by how many samples carry the keyword:

| Category | `librosa` F1 | `invariant` F1 | Support |
|---|---|---|---|
| bass | 0.641 | 0.584 | 2,399 |
| hi_hat | 0.601 | 0.468 | 2,143 |
| percussion | 0.423 | 0.418 | 1,467 |
| snare | 0.636 | 0.475 | 1,459 |
| kick | 0.643 | 0.629 | 1,318 |
| lead | 0.581 | 0.454 | 1,122 |
| cymbal | 0.682 | 0.519 | 962 |
| vocal | 0.471 | 0.138 | 704 |
| fx | 0.244 | 0.146 | 602 |
| pad | 0.329 | 0.081 | 402 |
| loop | 0.248 | 0.091 | 397 |
| clap | 0.583 | 0.337 | 293 |
| pluck | 0.000 | 0.036 | 105 |

`librosa` never predicts `pluck` at all, the smallest class at 105 samples. `fx` and `loop` score
low for a different reason: neither names a sound, so the keyword gathers samples with little in
common and no descriptor can group them. That is a property of the keyword table rather than of an
embedding, and it is why macro-F1 travels beside accuracy here.

The one place `invariant` nearly matches `librosa` is `kick` and `percussion`, where a sound's
identity sits in its envelope rather than its pitch. Everywhere pitch carries meaning -- `vocal`,
`pad`, `lead` -- the gap is wide, which is the same trade the retrieval table shows from the other
side.

## What this measures and what it does not

The category score describes 10.5% of the catalog. The note-event scores describe 97.5%, and 107,075
of those samples are struck at least eight times, which is the subset a pitch count can be read from
without the strike count deciding it. Transposition retrieval needs no labels at all and so speaks
for the whole catalog, which makes it the metric to trust when the three disagree.

No hand annotations are involved anywhere. The curation schema stays untouched.
