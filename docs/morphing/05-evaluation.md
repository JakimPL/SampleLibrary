# Evaluation

## Why this is Stage 1 rather than an afterthought

Two figures have been guiding decisions on this project:

- transposition retrieval, 95.5% for the invariant backend against 8.2% for librosa at −12 semitones;
- category coherence, 37.9% for librosa against 33.8% for the invariant backend.

Both came from throwaway scripts that were never committed. **They cannot be reproduced.** Worse,
the second was computed against the keyword categories, which cover 13,359 samples — 10.5% of the
catalog — and cover them unevenly: a sample carries a recognizable name when it came from a
well-organized module, so the labeled tenth is systematically the tidy tenth. And the vectors behind
both figures came from an experiment covering 25,000 samples, a fifth of the library.

None of that makes the figures wrong. It makes them unusable as a baseline, which is a different and
more annoying problem. The first thing to build is the harness that replaces them.

## Five metrics

Each names its data source and what it is sensitive to. The first three judge a representation as a
*descriptor* and apply equally to the existing backends; the last two judge it as a *code*.

### 1. Transposition retrieval

Take a held-out sample, resample it by a factor drawn from the corpus's own retuning range, embed
both, and ask whether the original is the resampled version's nearest neighbor among the whole
catalog.

Free, needs no labels, and directly measures the property
[`02-representation.md`](02-representation.md) is built around. Draw the factor from the measured
distribution rather than a round number: **an octave at the median, seventeen semitones at p90**,
with a long tail to six octaves. Report accuracy per semitone offset, since a method can be perfect
at ±2 and useless at ±12 — which is exactly the difference between the two existing backends.

### 2. Category kNN

Hold out a stratified split of the 13,359 keyword-labeled samples, predict each held-out sample's
category by k-nearest-neighbor vote in the embedding, and report per-category accuracy plus a
confusion matrix. The per-category breakdown matters: an earlier comparison found librosa ahead
overall while the deficit concentrated in cymbal, pad and vocal, and an aggregate number hides that.

State the coverage caveat wherever the number appears. It is 10.5% of the catalog, biased toward
tidy modules, and it is a proxy for the hand labels that do not exist yet.

**Split by equivalence class once `sample_relation` has rows**, so that bit-depth and resampled
variants of one waveform never straddle the split and inflate the score. Until equivalence detection
is redesigned — see [`06-alternatives.md`](06-alternatives.md) — every sample is its own class and
the split is a plain stratified one.

### 3. Note-event weak-label agreement

Derive per sample, from `note_event` joined through `(module_id, instrument_index, sample_slot)`:
the count of distinct sounded pitches, their span in semitones, and the total number of times the
sample was struck.

A 300-module probe found 41% of touched samples played at exactly one pitch, with the melodic
remainder spanning a median of 15 pitches over 27 semitones. That splits percussive from tonal
material over far more of the catalog than names reach, and it costs nothing to label. Measure
whether the embedding separates the two groups, and whether distance in it predicts pitch span.

This is also the tonality signal the project has wanted for a while, finally with something to
measure it against.

### 4. Reconstruction

Log-mel RMSE between a sample and its decoded reconstruction, against the scale established in
[`01-corpus.md`](01-corpus.md): Griffin-Lim alone reaches 4.72 dB median, and two unrelated real
samples sit at 22.70 dB. A codec plus vocoder wants to be much closer to the former than the latter.

**Report it split by vocoder and codec**, holding one fixed while the other varies. That is the
whole reason those are separate protocols, and it is how "the reconstruction sounds wrong" becomes
"the vocoder is losing the transient" rather than an argument.

**Carry the caveat with the number every time.** Log-mel RMSE is a magnitude measure, so it is blind
to phase, and phase is what Griffin-Lim estimates and where it fails. A fixed listening set spanning
the categories is part of this metric, not a nicety alongside it.

### 5. Morph plausibility

The metric that distinguishes a morph from a dissolve, and the one with no precedent to borrow.

For a morph at weight `t`, measure the decoded result's distance to each endpoint. A representation
where interpolation means something produces distances that move **monotonically** in `t`: as the
weight travels from A to B, the result travels away from A and toward B, smoothly. A degenerate
codec produces a crossfade — the result stays close to both endpoints throughout, or the distance
profile is flat in the middle, or it leaves the manifold entirely and the distance spikes.

Report the distance profile over `t` in a handful of steps, and flag non-monotonic runs. Sweep it
across a spread of pairs: within a category, across categories, and between a percussive and a
sustained sample, which is the hardest case and the most interesting one.

## Where results live

**Not in the repository.** The user was explicit: experiments are not registered there, and the
repository stays clean while the work stays experimental. MLflow is the candidate for run tracking,
with its store outside the repository.

The harness itself *is* repository code — library functions under `src/samplemorph/`, with tests,
following the precedent set by `sampleextract.equivalence.calibration`: the math lives in a tested
module, and `notebooks/equivalence_calibration.py` is a thin marimo notebook that only displays the
resulting numbers. A notebook here should do the same, computing nothing of its own.

One marimo trap worth knowing before it costs an afternoon: a cell auto-displays only a trailing
**expression**. Gating a display call inside an `if`/`else` statement computes the value and renders
nothing, silently. Use a trailing conditional expression — `(mo.audio(...) if ready else mo.md(...))`
— as the cell's last statement, and check the output with `marimo export html`.
