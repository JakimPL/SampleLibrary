# The pitch head: a transposition-equivariant coordinate trained on the library's own frames

[`26-pitch-glide.md`](26-pitch-glide.md) ends with a glide the ear accepted, driven by Hermes's
subharmonic summation. The reader is classical: it knows what a harmonic series looks like because
somebody wrote that down. [`24-learned-features.md`](24-learned-features.md) Step 2 asks whether the
library can teach a coordinate the same thing, and note 24's reading of the Step 1 failure says how:
a coordinate becomes position-like only when training pairs `(x, T_k x)` with a known `k` require it
to move by `k`.

This document is Step 2: the head, the run, and the gate it is judged by.

## The head

`samplemorph.coordinates.pitch_head` reads one constant-Q frame — 337 bins, three to the semitone
from 32.70 Hz — and answers with a distribution over 409 output bins of the same spacing, which
reach a full octave beyond the bins read at either end so every pitch a crop can hold has a bin to
land on.

- **The body** is three convolutions along the bin axis, each followed by a LayerNorm over the bins
  and a LeakyReLU. A convolution reads the shape of a harmonic series wherever it stands, and the
  normalization's statistics are the ones a move along the axis leaves alone.
- **The Toeplitz layer** maps the bins read onto the bins answered with one weight per offset
  between them, written as the correlation it is. Every output bin reads its inputs through the same
  weights, offset by where it sits, so moving the input along the axis moves the answer with it.
  That property holds by the shape of the map rather than by what the weights learn. It is PESTO's
  layer (Riou et al., 2023).
- **The readout** is the mass-weighted mean of the bins within a semitone of the peak, which answers
  between bins where a pitch lies between them. A sound's pitch is the median of its frames'
  answers weighted by the mass each gathered, so a frame answering an octave away moves it not at
  all while it lowers the agreement.
- **Reliability** is the mean mass times that agreement. Nothing about it is learned: two crops of
  one frame have an error near zero for a drum as for a bass, so a learned reliability would
  separate nothing.

36,806 parameters in all.

## What it is taught

No label names a pitch anywhere in the run. Each frame is read as three views — two crops of it,
each drawn at its own integer shift within a semitone's reach of twelve, and a second augmentation
of the first crop — and three terms price them:

- **equivariance**, PESTO's projection `φ(y) = Σ αⁱyᵢ`, whose ratio between two answers says how far
  one lies from the other without either saying where it is, under a Huber loss against `α^k`;
- **shift cross-entropy**, one answer against the other moved by the shift between the crops, which
  asks the same shape to arrive in the new place rather than merely the same center of mass;
- **invariance cross-entropy**, two augmentations of one crop against each other.

The augmentations declare what a pitch is not: a smooth envelope of four cosines up to ±15 dB, which
is every body a series can sound through; shelves cutting up to 40 dB away below and above drawn
bins, which is a fundamental lost to a small speaker at one end and an 8,363 Hz playback at the
other; and a noise floor lifted to up to 40% of the frame's own range. Every one of them is a gain
over the bin axis, so no partial moves.

**Calibration.** Nothing in the training says which pitch an output bin stands for, only that a move
of the input moves the answer with it, so one offset over the whole axis is what is left to measure.
It is read after training from plain harmonic tones on a grid across the register the library itself
sounds at, which Hermes reads off the pooled cache.

## The gate

Fixed here before the run, and decided by the user.

1. **Floor.** On reliable held-out samples, true retunings read a median `|Δ − k|` of at most
   0.1 semitone for `|k| ≤ 12` and at most 0.25 at 17. Octave and fifth jumps stay at or below 2%.
2. **Cross-sound consistency, which decides the glide:**
   - synthetic pairs of different timbres read their interval within 0.5 semitone at least 90% of
     the time, with at most 3% octave or fifth errors;
   - on real tonal samples where refined Hermes and pYIN agree, the head agrees at least 90% of the
     time;
   - the head does no worse than the better classical reader.
3. **Invariance.** Time stretch, level, 8-bit requantization and the envelope-first path drift a
   median of at most 0.1 semitone, with at most 2% octave flips.
4. **Reliability.** The top tercile's error is at most a third of the bottom tercile's. The glide's
   reliability threshold is fixed from this before any listening.

Reading 2 is the one this step exists for. A PESTO-style head regresses a shift within one sound
almost for free, and so does Hermes; the glide needs two different sounds to read on the same
harmonic.

## The run

`runs/pitch-2026-09-21/run.sh`, on the full catalog of 137,067 samples.

`cache-frames` read every sample twice — as stored and at a seeded true retuning within
±17 semitones — into 2.8 GB of float16 frames in **29 minutes** on eight workers. `train-pitch` ran
20 epochs over 130,213 samples, 6,854 held out by equivalence class, in 19 minutes on the GPU, at
93 seconds an epoch. `read-pitch` then read 200 held-out samples and 384 synthetic sounds through
the head and both classical readers: 13,797 trials.

The best epoch was the **fourth**. The held-out error fell for four epochs, then rose and oscillated
for the remaining sixteen, and the head that was kept reads a true retuning a median of 2.99
semitones away from where it sits.

## Readings

Median absolute error in semitones, over all trials of each kind:

| Reading | `pitch` (head) | `subharmonic` | `pyin` |
|---|---|---|---|
| True retunings | 0.68 | 0.01 | 0.00 (69% read) |
| Pitch-keeping changes | 0.99 | 0.01 | 0.00 |
| Synthetic families | 2.59 | 0.01 | 0.04 |
| Intervals across timbres | 5.00 | 0.00 | 0.10 |
| Where Hermes and pYIN agree | 8.94 | 0.03 | 0.03 |

Against the four readings of the gate:

1. **Floor — fails.** 0.68 semitone over all retunings, 0.33 in the head's own top reliability
   tercile, against the 0.1 asked. Octave jumps are 1.3%, better than Hermes's 3.6%; fifth jumps are
   13.0%, against the 2% asked.
2. **Cross-sound consistency — fails, and it is the reading the glide turns on.** Intervals between
   tones of different timbres read within half a semitone 21% of the time, against the 90% asked,
   with 17% fifth errors. On real tonal samples where both classical readers agree, the head agrees
   11% of the time and stands a median of 8.9 semitones away. Hermes reads the same 87 trials at
   0.03 semitone and agrees every time.
3. **Invariance — fails.** Time stretch, level, 8-bit rounding and the envelope-first path move the
   head's answer a median of 0.99 semitone, against the 0.1 asked, with 3.2% octave flips.
4. **Reliability — passes.** The top tercile's retuning error is 0.33 semitone against the bottom
   tercile's 2.33, a ratio of 0.14 against the third asked. Tones against noise bursts separate at
   an area under the curve of 0.99. The head knows when it is unsure; it separates TONAL from NOISE
   on real samples at 0.46, which is chance.

## What the head learned instead

Error against the true retuning grows almost exactly with the retuning itself: 0.49 semitone at
half a semitone, 1.0 at seven, 2.0 at twelve, 3.4 at seventeen. Read as a gain, the answer moves
about 80% of the way for the wide retunings and hardly at all for the narrow ones. The head has a
coarse, compressive sense of where a pitch lies and no resolution under a couple of semitones.

The stored head says why. Its answer is a hump, not a peak: the mass standing on the peak bin is
0.005 where a flat answer over 409 bins would stand at 0.0024, and that mass lies over the middle
third of the axis whatever the sound. A readout that gathers a semitone either way of the peak can
resolve nothing on a hump that wide, and the reliability it reports — 0.01 — is the honest
measurement of that.

The training terms say why again, and more exactly:

| Term | Epoch 1 | Epoch 20 |
|---|---|---|
| equivariance | 0.100 | 0.059 |
| shift cross-entropy | 5.75 | 5.73 |
| invariance cross-entropy | 5.84 | 5.80 |

`log 409` is 6.01, which is what either cross-entropy costs between two flat answers. **Both sat
there for twenty epochs.** The only term that moved is the equivariance ratio, and that is the term
a pair of broad answers satisfies nearly for free: `φ(y) = Σ αⁱyᵢ` reads two flat distributions at
almost the same value, so their ratio already stands near the 1 that a small shift asks for.

Both cross-entropies hold a prediction against a detached prediction of the same network. At the
start both are flat, and a flat target's optimum is a flat prediction — the pair is a fixed point of
its own objective, and nothing else in the loss carries enough of a position to break it. That is
the failure: not the inputs, not the pairs, but a stable flat answer the objective is content with.

## Verdict

**The head does not read pitch, and the refined-Hermes glide of [`26-pitch-glide.md`](26-pitch-glide.md)
stands as note 24's Step 0.** Three of the four readings fail, the one that decides the glide fails
by the widest margin, and the reading that passes says only that the head knows how little it knows.

Note 24's afterword asked which reading would fail, to say whether harmonic-aware inputs or real
retuned training pairs came next. The run answers neither: the cache holds real retuned pairs
already, and the head reads the constant-Q frames a harmonic reader reads. What failed is the
objective's own symmetry, which is measurable in the two flat cross-entropies above and is the
thing to fix before anything else is tried.
