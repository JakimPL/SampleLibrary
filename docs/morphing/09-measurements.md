# Measurements, taken on this machine

Everything here was measured against the real library on 2026-09-08, on the Linux machine that now
holds it. It supersedes figures in [`01-corpus.md`](01-corpus.md) and
[`08-prior-research.md`](08-prior-research.md) that were taken elsewhere, and it resolves the
frequency-axis question [`02-representation.md`](02-representation.md) left open.

## The corpus, re-counted

| Quantity | Recorded earlier | Measured here |
|---|---|---|
| Samples | 127,492 | **127,588** |
| Modules | 8,451 | 8,451 |
| Occurrences | 156,260 | 156,375 |
| Note events | 29,382,000 | 29,382,000 |
| Keyword-labeled samples | 13,359 (10.5%) | **13,373 (10.48%)** |
| Hashes carrying several rates | 6,972 (5.5%) | **6,978 (5.5%)** |
| Retuning spread p50 / p90 | 12.0 / 17.0 semitones | 12.0 / 17.0 |
| Looping occurrences | 36% | 35.9% |

The shape holds. Every figure the earlier documents state about what the library contains is
reproducible here.

## Note events reach the whole catalog

[`01-corpus.md`](01-corpus.md) left whole-catalog coverage unmeasured, and
[`02-representation.md`](02-representation.md) calls the 13,373 keyword labels "the largest
supervised signal available today". Measured over the full catalog in 11.8 seconds:

| Quantity | Value |
|---|---|
| Samples reached by a note event | **124,420 (97.5%)** |
| Struck at exactly one pitch | 47,054 (37.8% of those reached) |
| Distinct pitches p50 / p90 | 2 / 14 |
| Pitch span p50 / p90 | 5 / 26 semitones |

**Note events reach nine times as many samples as the names do.** They are the broad signal, and the
keyword categories are the narrow one.

The separation they give is a tendency rather than a split. Cross-tabulated against the keyword
categories:

| Group | Samples | Struck at one pitch | Median distinct pitches |
|---|---|---|---|
| Percussive (kick, snare, clap, hi-hat, cymbal, percussion) | 7,474 | 49.2% | 2 |
| Tonal (bass, lead, pad, pluck, vocal) | 4,606 | 18.4% | 6 |

Half of percussive samples are struck at more than one pitch, so a percussive-against-tonal label
read off the pitch count carries real noise. Pitch count and pitch span are worth treating as
continuous quantities an embedding either orders correctly or does not.

## What passes cost here

Measured single-core on a 24-core Linux machine reading from a local SSD, against
[`01-corpus.md`](01-corpus.md)'s figures from a Windows machine on a spinning disk.

| Pass | Recorded earlier | Measured here |
|---|---|---|
| Reading every sample's audio | ~52 min | **~1.5 min** |
| Mel spectrogram over the catalog | ~21.5 min | ~10.8 min |
| Constant-Q over the catalog | ~79 min | ~18.9 min |
| Constant-Q against mel | 4x | **1.75x** |
| `InvariantFeatureExtractor` over the catalog | — | ~21 min |
| `LibrosaFeatureExtractor` over the catalog | — | ~22 min |
| Griffin-Lim, 32 iterations | 531 ms/sample | 636-723 ms/sample |

**Reading the audio is 7% of a descriptor pass here, rather than the dominant cost.** The argument
in [`03-architecture.md`](03-architecture.md) for canonicalizing once into a memmap rests on the
older figure and does not apply to a single pass on this machine. It returns for training, where
the same audio is read once per epoch.

## The frequency axis, settled

[`02-representation.md`](02-representation.md) leaves mel against constant-Q open, to be "settled by
measurement rather than by argument". This is that measurement: 60 real samples between 4,000 and
200,000 frames, seed 7, each canonicalized as stored and again after being read at eight retunings
between -17 and +17 semitones, through the committed `samplemorph.measurement` functions.

A third axis is measured alongside the two the document names: a **log-frequency reading of the
short-time Fourier magnitude**, which is exactly logarithmic like constant-Q while inverting through
the ordinary Fourier grid like mel.

### How much of a retuning the grid absorbs

`explained` is the fraction of the distance between two unrelated samples' grids that
canonicalization removes. `translation error` is how far the conditioner's reported retuning sits
from the retuning actually applied, and `exact` is the share landing within half a semitone.

| Axis | Explained | Median translation error | Exact |
|---|---|---|---|
| **constant-Q, 36 bins/octave** | **65%** | **0.00 semitones** | **59%** |
| Log-frequency Fourier, 24 bins/octave | 55% | 1.62 semitones | 22% |
| Mel, 128 bands | 40% | 6.16 semitones | 4% |

Per retuning, as median grid distance and median translation error in semitones:

| Axis | -17 | -12 | -7 | -3 | +3 | +7 | +12 | +17 |
|---|---|---|---|---|---|---|---|---|
| constant-Q | 0.168 / 2.0 | 0.124 / 0.0 | 0.096 / 0.0 | 0.056 / 0.0 | 0.059 / 0.0 | 0.093 / 0.0 | 0.109 / 0.0 | 0.164 / 0.5 |
| log-frequency | 0.198 / 9.2 | 0.164 / 4.2 | 0.130 / 1.0 | 0.098 / 1.0 | 0.095 / 1.0 | 0.132 / 1.5 | 0.170 / 1.8 | 0.203 / 2.0 |
| mel | 0.200 / 9.9 | 0.186 / 7.5 | 0.154 / 4.8 | 0.118 / 3.0 | 0.117 / 3.0 | 0.154 / 4.4 | 0.186 / 8.2 | 0.209 / 8.0 |

**Constant-Q is exact from -12 through +12 semitones, which covers the corpus's own retuning range
through its p90.** The other two axes are not, and the reason is resolution rather than geometry:
the log-frequency reading is built from a 1,024-point Fourier window whose bins are 43 Hz apart, so
in the bass its logarithmic bands are interpolated from too few distinct values for the strongest
band to be located precisely. Constant-Q spends a longer window on low bands by construction and
finds the same band every time.

That matters because the estimate is what the alignment applies. A conditioner wrong by 1.6
semitones leaves two samples' grids misaligned by 1.6 semitones, and a morph between them smears
across that gap.

### How closely each axis reconstructs

The same 60 samples, canonicalized and restored, then made audible two ways: handed the source's own
phase, and having phase estimated by Griffin-Lim. Distances are log-mel RMSE in decibels against the
original audio, and the yardstick is the 21.72 dB between two unrelated samples.

| Axis | Oracle phase | Estimated phase | Cost of estimating phase | p90 | Worst |
|---|---|---|---|---|---|
| Log-frequency Fourier | **6.33** | **7.25** | 0.92 | 17.07 | 28.81 |
| Mel | 6.77 | 7.47 | 0.70 | 15.37 | 30.43 |
| Constant-Q | 8.48 | 9.49 | 1.01 | 19.83 | 48.60 |

Two findings, both of which change what the roadmap should spend effort on.

**Estimating phase costs 0.70 to 1.01 dB. The representation costs 6.3 to 8.5 dB.**
[`04-roadmap.md`](04-roadmap.md) makes "is Griffin-Lim good enough?" the gate that decides whether a
learned vocoder is worth training. Measured against an oracle handed the true phase, Griffin-Lim
gives up about one decibel, and the frequency axis and the fixed grid give up six to eight. A
learned vocoder can recover about a decibel; raising the analysis resolution can recover several.
The magnitude measure is blind to phase and only listening settles how a smeared transient sounds,
so the gate stands -- but the effort is better spent on resolution.

**The upper decile approaches the unrelated-sample scale on every axis.** A median of 7 to 9 dB
against 21.72 dB is comfortable, and a p90 of 15 to 20 dB is not. Some samples reconstruct poorly,
constant-Q worst among them. This is the open question this measurement raises, and the frame-count
decile each trial records is where to start looking.

### What was chosen, and what stays registered

**Constant-Q at 36 bins per octave is the default canonicalizer.** The design turns on removing a
retuning from the grid and carrying it as a conditioner, and constant-Q is the only axis measured
here that locates the retuning exactly across the corpus's own range. Its reconstruction sits 2.2 dB
behind the log-frequency reading, which is a real cost and a small one beside the 21.72 dB scale.

The log-frequency Fourier axis and the mel axis stay registered. The first is the reconstruction
leader and the natural place to test whether a longer analysis window fixes its bass resolution; the
second is the reference the other two are measured against.

## The first audio

A constant-Q canonicalizer, a 256-component principal-component codec fitted over 2,000 real
samples, a Griffin-Lim vocoder and a linear morpher, rendered end to end. The codec holds **93.1%
of the fitted body's variance** and takes about 80 seconds to fit; a seven-file listening set
renders in about three seconds.

### The morph path is a path, not a wash

The standing worry is that a codec produces a crossfade -- both sounds at once -- which is the
result this project built once before and rejected. Measured on two real pairs, the decoded grid's
distance to each endpoint moves evenly across the weight:

| Weight | To the first | To the second |
|---|---|---|
| 0.00 | 0.0000 | 0.2946 |
| 0.25 | 0.0726 | 0.2222 |
| 0.50 | 0.1465 | 0.1481 |
| 0.75 | 0.2206 | 0.0740 |
| 1.00 | 0.2946 | 0.0000 |

Both pairs travel away from the first sample and toward the second at every step, with no step
sitting closer to both than the endpoints sit to each other. `samplemorph.measurement.plausibility`
holds this as a standing check.

### Reconstruction has a good median and a bad tail

Over 40 real samples, the round trip through an exactly invertible codec lands at a **median of
8.71 dB** against the roughly 22 dB that separates two unrelated samples. The upper decile reaches
**16.67 dB** and the worst case **38.19 dB**, which is further from its own original than an
unrelated sample would be.

Two things were tested and ruled out as the cause:

- **The measure's own floor.** Clamping the log-mel comparison 80 dB below each peak leaves the bad
  cases where they were, so the error is not a difference between bands too quiet to hear.
- **Phase estimation.** The failing cases fail as badly when handed the source's own phase, so the
  loss happens before synthesis.

Sweeping the dynamic range the grid spans moves the failures around without removing them:

| Dynamic range | Median | p90 | Worst |
|---|---|---|---|
| 60 dB | 8.71 | 16.67 | 38.19 |
| 80 dB | **7.16** | 19.67 | 34.00 |
| 100 dB | 9.70 | 27.35 | 32.89 |
| 120 dB | 12.96 | 37.58 | 42.27 |

80 dB gives the best median and a worse upper decile, so the default stays at 60 dB until something
decides it. One bass guitar sample improves from 22.41 dB to 9.42 dB at 80 dB, which says the
dynamic range is part of the story for at least some failures.

**The tail is the open question this stage hands on.** Each trial records the frame count it came
from, and the first thing to check is whether the failures concentrate in the long samples the
64-column time axis compresses hardest.

## Corrections to earlier documents

1. **[`02-representation.md`](02-representation.md): "Mel inverts more cleanly" than constant-Q.**
   Measured through one shared synthesis path, mel reconstructs at 7.47 dB and constant-Q at 9.49,
   so mel does invert more cleanly here -- but by 2 dB rather than decisively, and constant-Q wins
   the translation property by a margin that matters more to this design.
2. **[`02-representation.md`](02-representation.md): constant-Q "costs about four times a mel
   spectrogram".** Measured at 1.75x. The cost argument for mel is much weaker than recorded.
3. **[`01-corpus.md`](01-corpus.md): "Reading the audio dominates every analysis pass."** It is 7%
   of one here.
4. **[`01-corpus.md`](01-corpus.md) and [`05-evaluation.md`](05-evaluation.md): "the worst
   reconstruction still beats the closest unrelated pair."** Reproducing the original Griffin-Lim
   experiment gave a worst reconstruction of 12.03 dB against a closest unrelated pair of 10.71 dB,
   so the claim fails. The median headroom is real; the extreme-case headroom is not, and the same
   pattern shows in the p90 column above.
5. **[`02-representation.md`](02-representation.md) and [`05-evaluation.md`](05-evaluation.md): the
   note-event signal "separates percussive from tonal material structurally".** It correlates with
   percussiveness and does not separate it; see the cross-tab above.
6. **[`02-representation.md`](02-representation.md): the keyword categories are "the largest
   supervised signal available today".** Note events reach nine times as many samples.
7. **[`07-environment.md`](07-environment.md) and [`04-roadmap.md`](04-roadmap.md): `make extract
   SHARD=0/4`.** Sharding was replaced by an internal worker pool; the flag is now
   `make extract WORKERS=n`. `make database` also now creates the role and databases that document
   asks for by hand.
8. **[`03-architecture.md`](03-architecture.md): `Experiment.params` is "round-tripped as structured
   JSON".** It is `json.dumps` into a `String` column, so Postgres holds opaque text and no JSON
   operator reaches inside it.

## How to re-derive any of this

The equivariance and reconstruction figures come from `samplemorph.measurement`, which is committed
and tested. `notebooks/canonical_representation.py` displays them and computes nothing of its own.
The corpus counts are plain catalog queries, given in [`01-corpus.md`](01-corpus.md).
