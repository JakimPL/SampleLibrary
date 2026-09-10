# Perceptual readings on the representation ladder

[`17-scoring-and-evaluation.md`](17-scoring-and-evaluation.md) laid out the instruments; this is
what they read on real material, before any ear has judged it. Three readings were built and
measured on the ladder listening set that was already rendered (`listening/ladder-2026-09-10/`,
twelve probes at their heard rates, six rungs each) with no new synthesis:

- **`loudness_delta`** — ITU-R BS.1770 integrated loudness of a reconstruction minus its reference,
  in LU, K-weighted, so inaudible low frequencies do not inflate it. The files are peak-normalized
  to 0.98 by the renderer, so this is loudness *at matched peak* — which is what the ear heard.
- **`modulation_spectrum_distance`** — the principled form of the flutter screen: a gammatone bank
  at the heard rate, each channel's envelope compressed and read as a modulation spectrum, weighted
  through the two lobes a listener hears a gargle on. It reports a **signed** depth per lobe
  (fluctuation, 1–20 Hz peaking at 4 Hz; roughness, 20–150 Hz peaking at 70 Hz) and an **unsigned**
  per-bin distance.
- **`sound_type_reading`** — tonal, percussive or noise from three continuous readings, so every
  table below can be split the way the user asked: by what kind of sound it is.

Everything is against `1_original` at the heard rate; the same tables against `2_clean_oracle`
(phase isolated) differ by less than the reading's own spread and are in `metrics.csv`.

## The energy leaves at phase estimation, and mostly from percussive material

The user heard reconstructions come back quieter. Every earlier metric normalized that away
([`17`](17-scoring-and-evaluation.md#loudness-the-axis-the-panel-was-missing)); this is the first
number that sees it, and it locates it.

| Rung | Loudness delta, LU, median [p25 p75] |
|---|---|
| 2 clean oracle (true phase) | **−0.02** [−0.07 −0.01] |
| 3 clean PGHI | **−1.07** [−2.69 −0.58] |
| 4 + log-frequency round trip | −1.51 [−2.73 −0.90] |
| 5 + 64-column time squeeze | −1.41 [−1.92 −0.35] |
| 6 production Griffin-Lim | **−2.69** [−4.01 −1.29] |

The true phase loses nothing. The loss begins the moment phase is *estimated* — clean PGHI on an
untouched STFT already costs a decibel — and Griffin-Lim on the production grid costs nearly three,
four at the lower quartile. So the drop is a synthesis effect, as the analysis predicted: an
estimated phase produces a peakier waveform, and at matched peak a peakier waveform is a quieter one.

Split by sound type, the loss concentrates exactly where the user's Stage 2 verdict put it:

| Rung | percussive (n=3) | tonal (n=6) | other (n=3) |
|---|---|---|---|
| 3 clean PGHI | **−3.23** | −0.76 | −1.19 |
| 4 round trip | **−3.99** | −0.82 | −2.27 |
| 5 time squeeze | −2.26 | −0.31 | −1.47 |
| 6 production GL | **−4.51** | −2.15 | −2.13 |

A struck sound loses three to five LU under every phase estimate; a held one loses under one with
PGHI and two with Griffin-Lim. This is the "loses transients and energy" the user described, and
now it is a number with a sign.

## The gargle reads as redistributed modulation, on the fluctuation axis

| Rung | modulation distance (unsigned) | fluctuation excess | roughness excess | flutter (old screen) | held-out dB |
|---|---|---|---|---|---|
| 2 clean oracle | 0.002 | +0.0001 | +0.0002 | −0.000 | 0.59 |
| 3 clean PGHI | 0.095 | +0.0012 | −0.0006 | −0.001 | 2.74 |
| 4 round trip | **0.171** | **+0.0074** | −0.0024 | **+0.098** | 6.87 |
| 5 time squeeze | 0.181 | +0.0007 | **−0.0038** | +0.071 | 8.11 |
| 6 production GL | **0.246** | **+0.0117** | +0.0026 | +0.134 | 7.54 |

Four things this says.

1. **The unsigned distance orders the ladder and reproduces its finding.** Clean PGHI reads 0.095;
   the log-frequency round trip nearly doubles it to 0.171; Griffin-Lim on the production grid reads
   0.246. The old flutter screen agrees on the ordering (−0.001, +0.098, +0.134), and the two agree
   that PGHI on a clean STFT is where the artifact is *smallest*, which is the ladder's central
   claim ([`17`](17-scoring-and-evaluation.md), the plan's status section).
2. **The signed excesses are small beside the distance.** The round trip adds +0.007 of lobe depth
   on average while moving 0.171 of per-bin depth around. On real material the reference already
   carries micro-modulation — decay, vibrato, texture — and the gargle *rearranges* it far more than
   it adds to it. The sign is still informative where it is clear: the round trip and Griffin-Lim
   read positive on fluctuation (added warble), the time squeeze reads **negative on roughness**
   (fast modulation smoothed away), and on percussive material the squeeze reads −0.007 and the
   round trip −0.008 roughness — the transient cost the shape metrics were suspected of
   under-weighting, now visible as erased fast modulation on struck sounds.
3. **On this material the gargle lives on the fluctuation axis, not roughness.** Roughness reads
   within ±0.004 on every rung. That is consistent with the psychoacoustics rather than against it:
   most of these probes are heard at 8 kHz with content below 3 kHz, where the auditory filter is
   narrow enough to *resolve* the sidebands a 70 Hz modulation would make, so the ear hears a slow
   swept comb as warble. The roughness lobe stays in the panel for material where it applies.
4. **Fluctuation excess stays under the detection floor as an average.** The floor is 0.017 in the
   compressed domain; the round trip's +0.007 is a loudness-weighted mean over every channel and
   moment, and the comb is concentrated in a few. The per-probe rows in `metrics.csv` are the place
   to read the peaks; the study in the next section is where the number meets the ear.

One correction to the design in [`17`](17-scoring-and-evaluation.md): the first build subtracted
the detection floor from every modulation *bin*, which zeroed precisely the broadband modulation a
swept comb produces. The floor is a statement about the modulation a listener hears as a whole, so
it now stands beside the lobe depth as its yardstick rather than being taken out of each bin, and a
sinusoidal modulation at a lobe's peak reads its own depth.

## The sound-type reading, on the ladder and against the keyword categories

On the twelve ladder originals the reading agrees with the user's tags on nine of nine explicit
ones — three percussive (0.61, 0.51, 0.71 against the 0.5 bar), six tonal (every one reads 0.00
percussiveness) — and reads one of the three "other" probes as noise and the other two, whose
harmonicity is 0.99, as tonal. Two lessons came from getting there:

- A **percussive loop** reads as a held sound to any single-hit model, since its level is flat across
  the clip. The reading now cuts the clip into strikes wherever the level climbs 12 dB within 20 ms
  and scores each strike on its own, so a loop of hits reads hit by hit. A third of this corpus's
  occurrences loop, so this is a property of the material, not an edge case.
- Decay is judged in **absolute time**, not as a share of the clip: the two kicks fall 12 dB in 127
  and 173 ms, the tonal pluck beside them in 809 ms, and a share-of-clip reading blurs that by clip
  length.

Against a seeded draw of keyword-labeled samples (forty per category where the names allowed),
leads read tonal 36/36, pads 21/21, vocals 27/28, basses 33/40; snares read struck or noise 31/40.
Kicks and cymbals split along their ring — a cymbal is a strike followed by a second of sustain,
and the reading calls that sustained, which is the acoustically honest answer and a different
question from what the keyword names. The keyword table is a first-pass heuristic
([`09-measurements.md`](09-measurements.md)); the reading is calibrated on the ladder's tags and
sanity-checked here, with its three readings kept beside the verdict so a disagreement can be read.

## What this decides, and what waits for the ear

- **The loudness reading is adopted.** It sees an effect every other number normalized away, its
  sign is right, and its per-type split matches what the user heard. It goes into every future
  vocoder table beside the shape readings.
- **The unsigned modulation distance is adopted as the ordering instrument**, and the signed lobe
  depths as the explanation of *which way* a rung erred. Whether their ordering matches the ear's
  is the calibration study's question.
- **The old flutter screen is retained** for continuity; its frame-rate envelope at the typical
  8363 Hz heard rate has a Nyquist near 16 Hz, so it is a fluctuation-lobe screen by arithmetic.

The study itself needs listening: the user rates the five reconstructions of each of the twelve
probes for gargle severity and for "quieter", in the same sitting as the ladder verdict, and every
reading in `metrics.csv` is rank-correlated against those labels, overall and per sound type. That
table completes this document.

## How to re-derive any of this

`runs/night-2026-09-10/scripts/ladder_measure.py` (beside the library, outside the repository)
reads the rendered set and writes `listening/ladder-2026-09-10/metrics.csv`; the readings it calls
are `samplemorph.measurement.loudness`, `samplemorph.measurement.modulation_spectrum` and
`samplecore.auditory.sound_type`, committed and tested. The keyword calibration is
`sound_type_calibration.py` in the same folder, a read-only draw of seed 11.
