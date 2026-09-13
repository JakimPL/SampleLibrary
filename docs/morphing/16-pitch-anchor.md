# Where a morph's pitch goes, and the band alignment should hold on to

Listening to the sets from [`15-conditioned-codec.md`](15-conditioned-codec.md) found that a
morph between two samples playing one note does not keep that note. This is why, measured, and
the alignment rule that puts the pitch of a morph on the line between its endpoints' by
construction.

## What alignment anchors on

Every canonical grid is translated so that one band sits at the geometry's reference band, and
the translation leaves the picture as `translation_semitones`. Which band moves there has been the
**loudest band** of the time-averaged grid since [`02-representation.md`](02-representation.md):
it exists for every kind of material, percussion included, and it moves with a rate change by
exactly the change, which is what makes the picture rate-invariant.

The loudest band of a harmonic sound is whichever partial carries the most energy, and that is
not the same partial from one instrument to the next. Over a 400-sample draw with a time-domain
pitch estimate as the reference, the loudest band sits on the fundamental for 45% of the steady
tonal samples, on a harmonic -- an octave, an octave and a fifth, or two octaves up -- for 39%,
and elsewhere for the rest.

## What that does to a morph

A morph interpolates `translation_semitones` and the playback rate in the log domain, so the
heard pitch of the *anchor* runs straight from one endpoint's to the other's. The decoder,
trained on grids whose anchor sits at the reference band, decodes a midpoint with its energy
there too. When the two anchors are different partials, the fundamental of the midpoint is
therefore somewhere else than halfway between the two fundamentals.

Measured on the piano-to-strings set, reading each rendered file at its stated rate: the piano's
anchor is its second harmonic, twelve semitones above its fundamental, and the strings' is its
fundamental. The heard pitch along the path, in MIDI note numbers, through the conditioned codec:

| 0 | 0.25 | 0.5 | 0.75 | 1 |
|---|---|---|---|---|
| 72 | **78** | 72 | 66 | 60 |

The path first climbs by a tritone and then descends, when the straight line would be 72, 69, 66,
63, 60. The other pairs are anchored a similar distance apart: the pluck's anchor sits 11.6
semitones above its fundamental and the bass's on it, the pad's 28 semitones above its and the
kick's on it. This is a property of the alignment, so no training of the descriptor, the codec or
the vocoder moves it.

## Anchoring on the fundamental

`Anchor.FUNDAMENTAL` (`samplemorph.geometry`) scores every band as a candidate fundamental by
the magnitude at each of its first eight multiples, the higher ones counting less by 0.84 a step:
the subharmonic summation of Hermes (1988), read over the grid's time average as linear
magnitude. A harmonic sound scores highest at its fundamental even when a higher partial is
louder, since that partial's own multiples miss the odd harmonics; a sound whose fundamental is
weak or absent still scores highest there through the partials above it; noise scores highest at
the lowest band carrying its energy, which moves with a rate change exactly as a fundamental
would. The rule lives in `samplemorph.canonicalizers.common.fundamental_band`, and every geometry
records which anchor its grids were aligned by, so a stored model, cache or descriptor rebuilds
the canonicalizer that made it.

Over the same 400-sample draw, on the steady tonal samples:

| Anchor | On the fundamental | On a harmonic | An octave below | Elsewhere |
|---|---|---|---|---|
| Loudest band | 45% | 39% | 0% | 15% |
| Harmonic sum, linear magnitude, 8 harmonics at 0.84 | **70%** | **17%** | 2% | **12%** |

Nine variants of the sum were measured -- over the normalized decibels, floor-subtracted,
spectrally whitened at two widths, over square-root and linear magnitude, and gated to local
peaks at four thresholds -- and the plain sum over linear magnitude was the best on every column
but the octave-below one, where it costs two percent. The reference is a median pitch estimate
that itself errs on some chip material, so the percentages are a comparison between rules rather
than absolute accuracy.

## The path as a reading

`samplemorph.measurement.plausibility` now reads pitch along a morph beside the energy share and
the spread: each step's pitch, found the way the alignment finds a fundamental on the grid restored
from the decoded image, against the line between the endpoints' pitches, and
`largest_pitch_deviation` is the worst step. The playback rate a render is written at moves in a
straight line with the weight too, so a deviation measured on the grids is the one heard. A
lossless morph between two notes an octave apart, one with a loud second harmonic, deviates by
more than three semitones on the loudest-band anchor and under one on the fundamental anchor,
which `tests/samplemorph/test_morphers.py` holds to.

## What it costs, and what stays open

The anchor is a property of the grid, so a change to it is a change to every grid: the grid
caches, the descriptor and the codec are rebuilt on it (`samplelibrary morph cache-grids
--anchor fundamental`, then the descriptor and codec passes as before), roughly two and a half
hours of machine time in all. The phase model reads magnitudes restored to the Fourier axis,
which the anchor leaves as they were, so it carries over.

Open, in order:

- **A rebuilt chain on the fundamental anchor**, and the pitch path measured again on the same
  four pairs. That is the test of this stage.
- **A sweep over the sum's decay and harmonic count**, which the measurement above did not reach.
- **The reference band's position.** With the fundamental at 440 Hz, the picture below it is
  empty but for noise; a lower reference would give the harmonics more room at the top.
