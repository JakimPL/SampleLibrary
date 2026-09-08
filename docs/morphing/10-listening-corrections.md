# What listening found, and what it corrects

The first listening set was rendered on 2026-09-08 and judged the same evening: *"gargling and of
poor quality… the artifacts are in every reconstruction, so the problem is rather fundamental. Not
good enough, far from it, but interesting."*

That verdict was right, and it contradicted the numbers in
[`09-measurements.md`](09-measurements.md). This document records why the numbers missed it, the two
defects the ear pointed at, and the loss budget that replaces the one in
[`09-measurements.md`](09-measurements.md).

## The yardstick was the first defect

Two measurements decided the representation, and neither could see the failure.

- **Log-spectral distance is blind to phase.** [`09-measurements.md`](09-measurements.md) reports
  phase estimation costing 0.70–1.01 dB against a representation cost of 6.3–8.5 dB, and concludes
  that effort belongs on resolution rather than on a vocoder. Gargling is a phase-coherence
  artifact. That conclusion was never supported by the measurement it cited.
- **A mel yardstick hides a wrong spectrum.** `log_mel_distance_db` averaged the reconstruction into
  128 mel bands before comparing. A filterbank band is wide where the error was largest, so a
  spectrum whose shape was wrong by 20 dB was reported as a 9.49 dB round trip.

Both are now replaced by `held_out_distance_db`: a linear Fourier analysis, fixed and independent of
whichever axis produced the audio, with every band the same width. Under it, unrelated samples sit
at **21.5–22.5 dB**, which is the scale every figure below is read against.

## Defect 1 — the constant-Q axis was synthesized from

[`09-measurements.md`](09-measurements.md) chose constant-Q as the default axis on alignment accuracy
(65% explained, 0.00 st error, 59% exact) while recording that its reconstruction was the worst of
the three (9.49 dB against log-frequency's 7.25). It called the trade worth making. It was not.

A constant-Q bin states the amplitude within a band whose width grows with its center frequency. A
Fourier bin states it within a band of one fixed width. Reading constant-Q magnitudes onto the
linear Fourier grid therefore hands the vocoder a spectrum with the wrong shape — measured against
the same signal's Fourier magnitude, the two differ by roughly 20 dB over the lowest octaves and 25
dB elsewhere.

Rebuilding the pipeline one stage at a time, on the oboe the set was rendered from:

| Stage | Constant-Q | Log-frequency |
|---|---|---|
| Griffin-Lim on the untouched magnitude | 2.26 | 3.38 |
| Frequency axis alone, true phase | 3.92 | 4.74 |
| Time axis alone, true phase | 2.07 | 0.72 |
| **Whole pipeline, true phase** | **24.00** | **5.09** |
| **Whole pipeline, Griffin-Lim** | **23.12** | **8.90** |

The constant-Q reconstruction sat *at* the distance between unrelated samples. It carried about as
much of its original as a randomly chosen other sample would — which is what "every reconstruction
is wrong" sounds like. Giving it perfect phase changed nothing, because the magnitude was the
problem.

`constant_q` stays registered and stays the most accurate axis for locating a retuning. It is now
recorded as an analysis axis: `SYNTHESIS_CANONICALIZER_NAMES` names the axes audio is rendered from,
and a test asserts the measured fact that constant-Q sits further from its source than unrelated
content does.

## Defect 2 — alignment destroyed what it moved past the edge

Alignment translates the picture so its strongest band lands on the reference band, and the
translation travels out as a conditioner. The grid was exactly as tall as the analysis range, so a
translation of *n* bands pushed *n* bands out of the picture and filled *n* bands with silence.

The shift is largest for material furthest from the 440 Hz reference band, which is bass — the
largest keyword category. A bass guitar needing +36 semitones lost every band above about 2.7 kHz.
Measured on one, with perfect phase: **20.09 dB**, again at the unrelated-sample scale.

Every geometry now reserves `shift_headroom_bands` at both ends, holding the largest translation it
allows, and `restore_columns` crops back to the analyzed range. Alignment became exactly lossless:
the unaligned and aligned rungs now report identical distances.

| Sample | Before | After |
|---|---|---|
| bass guitar | 20.09 | **3.56** |
| oboe | 6.82 | **5.09** |
| snare | 5.14 | **4.91** |
| pad | 3.89 | **3.89** |

The grid grew from `band_count` rows to `band_count + 2 × headroom` — 338 to 626 at 36 bins per
octave with a 48-semitone cap. Fitting 256 components over 2,000 samples takes 13 seconds, and the
codec holds 97.3% of the variance where it held 93.2%.

## Defect 3 — the axis was sampled where it should have been averaged

The corrected renders were judged again and still carried an artifact, described as *"an unaligned
other frequency… rendered in windows of frequencies unmatched with the fundamental"*, and likened to
an Amiga ProTracker sample stepped through with `901 902 903` while the tempo runs against the
playback rate. Rung by rung: `2_griffin_lim_only` was clean, while rungs 3, 5, 6 and 7 carried it,
and on bass only rung 7 did.

That pattern names the stage exactly. Rung 2 is Griffin-Lim on the untouched Fourier magnitude, so
the phase estimate was never the source. Rung 3 is the frequency-axis round trip alone, and it read
each log band from its own center frequency by interpolation:

| Band | Frequency | Linear bins the band spans |
|---|---|---|
| 144 | 523 Hz | 0.94 |
| 180 | 1046 Hz | 1.87 |
| 252 | 4186 Hz | 7.49 |
| 324 | 16742 Hz | 29.94 |
| 337 | 21504 Hz | 38.46 |

Above 559 Hz a band covers more than one Fourier bin, reaching 38 at the top of the range, so
reading the band at its center kept one bin in thirty-eight. Sampling a spectrum that sparsely is
decimation along the frequency axis with nothing filtering it first, and decimating a spectrum folds
the frame back on itself in time. Each frame repeats at a period set by the Fourier grid rather than
by the sample's pitch, which is what the ProTracker comparison describes and why bass — whose energy
sits mostly below the crossover — was the one sample it spared.

Each band now takes a weighted mean across its own width, through `triangular_weights` in
`samplecore.waveform`. The round trip improves on every probe: oboe 4.74 → 4.14, bass 3.66 → 2.94,
snare 4.60 → 3.63, pad 3.80 → 3.04. Both readings are rendered side by side as `3_log_axis_only`
and `3b_log_axis_by_sampling`.

The time axis carried the same defect: `to_time_columns` read 194 analysis frames onto 64 columns by
interpolation, stepping over the frames between. It now averages across each column's span, through
`average_to_fraction_points`. `resample_to_fraction_points` keeps its interpolating behavior, since
`samplecloud`'s invariant backend is built on it and its vectors are already extracted over the whole
catalog.

Averaging the time axis raises the held-out distance slightly — oboe 0.72 → 0.88, pad 1.10 → 1.25 —
because a magnitude yardstick reads a low-pass as error and reads aliasing as agreement. That is the
same blindness [the yardstick section](#the-yardstick-was-the-first-defect) records, and it is why
this change rests on the mechanism and on listening rather than on the number.

## Where the ceiling actually sits

A third listening round settled what the remaining artifact is. On the ladder, *"besides the
original, only 1, 2 and 4 have clarity, 7 still is the worst"*, and the point-sampled reading was
*"worse in general than 3, introduces some chorus-like combined with slight tremolo effect"*.

Read against what each rung is:

| Rung | What it is | Judged |
|---|---|---|
| 1 | Fourier round trip, true phase | clear |
| 2 | Griffin-Lim on the untouched magnitude | clear |
| 3 | frequency axis alone, true phase | carries it |
| 3b | the same, read at band centers | worse |
| 4 | time axis alone, true phase | clear |
| 7 | whole pipeline, Griffin-Lim | worst |

Rung 2 being clear rules the phase estimate out as the source. Rung 4 being clear rules the time
axis out. **Rung 3 carries the artifact while holding the source's own phase**, so what remains is
the frequency axis, and no phase estimate can recover from it.

The averaging fix helped and did not finish the job. It removed the folding that made 3b sound
chorused, and what is left is the resolution the axis has: 338 bands stand where 1,025 Fourier bins
were, and the reduction falls entirely above the crossover. Between 559 Hz and Nyquist, several
harmonics land inside one band, so the band records their sum and synthesis spreads that sum back
across the band's width. Partials come back as a plateau rather than as lines, and the flanging is
what that sounds like after overlap-add.

The crossover is where a log band equals a Fourier bin, and both the window length and the band
density move it:

| Analysis and grid | Crossover | Bands | Grid rows | oboe | snare |
|---|---|---|---|---|---|
| 2048 / 36 per octave | 559 Hz | 338 | 626 | 4.04 | 3.59 |
| 1024 / 36 per octave | 1118 Hz | 338 | 626 | 3.70 | 2.95 |
| 512 / 36 per octave | 2237 Hz | 338 | 626 | 4.83 | 2.79 |
| 2048 / 72 per octave | 1118 Hz | 676 | 1252 | 2.95 | 3.12 |
| 2048 / 144 per octave | 2237 Hz | 1353 | 2505 | 2.14 | 2.48 |

A shorter window widens the bins and suits percussive material; more bands per octave narrows the
bands and suits both, at a grid four times taller. The two knobs trade against each other because a
fixed analysis window holds one absolute resolution while a log axis asks for one proportional to
frequency, which is the same tension `constant_q` resolves for analysis and cannot resolve for
synthesis.

This reframes what a vocoder is for. Phase retrieval recovers phase for a magnitude that some real
signal produced, and the magnitude this grid holds is not one: above the crossover its harmonic
structure has been averaged away. Recovering that structure means putting detail back that the
representation does not carry, which is a decoder's job rather than a phase estimator's. Griffin-Lim
reaching its ceiling here is the expected result rather than a defect in it.

## The resolution that clears the bar

A fourth round judged `fft2048_bpo144` acceptable: *"in percussion you can get away with these
artifacts, but the general clarity may be a problem in the long run… it passes our initial bar."*
That verdict was given on the frequency-axis round trip carried by the source's own phase, so the
pipeline was measured again at that density to see what survives the rest of it.

| Rung | oboe | bass | snare | pad |
|---|---|---|---|---|
| 3 — frequency axis, true phase | 3.34 | 2.20 | 3.37 | 2.78 |
| 6 — whole representation, true phase | 3.41 | 2.22 | 3.46 | 2.89 |
| 7 — whole pipeline, Griffin-Lim | 7.26 | 6.67 | 6.79 | 7.34 |

The representation costs almost nothing beyond its frequency axis at this density, and alignment is
lossless again. Griffin-Lim adds 3.8 to 4.5 dB on top, which is now the whole of the remaining gap
and the subject of the next listening round.

### What the density costs

| Bands per octave | Alignment cap | Grid rows | Cells | Headroom share |
|---|---|---|---|---|
| 36 | 48 st | 628 | 40,192 | 46% |
| 144 | 24 st | 1,931 | 123,584 | 30% |
| 144 | 48 st | 2,507 | 160,448 | 46% |

The cap stays at 48 semitones because alignment accuracy is what lets a linear codec interpolate one
sound rather than two pitches, and at 144 bands per octave it reads 79% of retunings exactly with a
median error of 0.08 semitones, against 57% and 0.33 at 24 semitones.

Fitting 256 components over 2,000 samples at this grid takes 59 seconds and 9.7 GB, holding 97.7% of
the variance. That fits this machine and sets the point where a larger fitting body needs the
components built in batches or on the GPU.

### A band range that stopped short of Nyquist

Reading silence outside the band range turned out to discard audible content. The bands reached
21,504 Hz against a 22,050 Hz Nyquist, leaving 26 Fourier bins outside them, and a sample stored at
the nominal 44,100 Hz plays back at a fraction of it -- 21,504 Hz lands near 4 kHz for a sample
played at 8,363 Hz. The whole-pipeline distance rose from 4.64 to 7.81 dB before this was found.

The bands now reach Nyquist, through `bands_reaching_nyquist`. `constant_q` keeps the older rule as
`bands_below_nyquist`, since a transform building one wavelet per band asks every band to fit under
Nyquist.

## Defaults these findings changed

| Setting | Was | Now | Why |
|---|---|---|---|
| Default axis | `constant_q` | `log_frequency` | its bands state amplitude per Fourier bin |
| `DEFAULT_FFT_LENGTH` | 1024 | 2048 | exact translation 64% → 82% |
| `DEFAULT_BINS_PER_OCTAVE` | 24 | 144 | 36 settled the axis, 144 cleared the listening bar |
| `DEFAULT_DYNAMIC_RANGE_DB` | 60 | 100 | the 60 dB clip cost 2.5–3.4 dB |
| Grid height | `band_count` | `band_count + 2 × headroom` | alignment keeps every band |

Raising the FFT length beyond 2048 buys alignment (86% exact at 4096) and costs reconstruction, so
2048 is where the two meet. Time columns stay at 64: measured alone, that axis costs 0.4–1.1 dB,
which is the smallest term in the budget and the one least worth spending grid on.

## The loss budget that replaces the old one

Measured on four real samples through the corrected pipeline, against the 21.5 dB unrelated scale:

| Term | Cost |
|---|---|
| Log-frequency axis mapping | 3.7–4.7 dB |
| Time axis, 64 columns | 0.4–1.1 dB |
| Alignment | 0.00 dB |
| **Representation, true phase** | **3.6–5.1 dB** |
| Griffin-Lim phase estimate | +3.3–4.6 dB |
| **Whole pipeline** | **8.2–8.9 dB** |

**Phase is now the largest single term**, which reverses the conclusion in
[`09-measurements.md`](09-measurements.md) that effort belongs on resolution rather than on a
vocoder. Griffin-Lim costs 3.3–3.5 dB even on an untouched full-resolution magnitude, and running it
longer makes it slightly worse — 9.35 dB at 32 iterations, 9.46 at 100, 9.62 at 300. Iterating
further settles deeper into a solution for a magnitude field that no real signal produces, which is
the case for training a vocoder rather than tuning this one.

## What stays open

- **Whether the corrected audio is good enough.** The numbers improved by a factor of three on the
  worst material; only listening decides whether the artifact is gone or merely quieter.
- **The 3.7–4.7 dB axis mapping.** Reading the log-frequency bands onto the linear grid by
  interpolation is the largest representation term. A resolution that varies with frequency, or
  synthesizing on the log axis directly, would attack it.
- **Constant-Q for conditioners only.** It locates a retuning better than the log-frequency axis
  (89% exact against 82%). Estimating the translation on constant-Q and applying it to a
  log-frequency grid would take the accuracy without the synthesis defect.
