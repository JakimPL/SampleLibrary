# Audio transport: morphs that move features

The user, after working with the morph in the application: "in many cases it feels like a regular
convex blend of two samples", and then "the entire premise of a morpher falls with the current
approach … the path has to move features." This document records the measurement that confirmed
the claim, the morph built in answer, and the comparison that decides whether it replaces the
latent route.

## Why the grid path is a crossfade

The production route is: the log-frequency grid in normalized decibels, a 256-component linear
codec, a straight line between two latents, the restorer, phase gradient heap integration. Every
step up to the restorer is affine, so the decoded midpoint *is* the decibel blend of the two decoded
ends, clipped to the grid's range. A blend in decibels is a geometric mean of magnitudes: whatever
only one sound holds falls by half the grid's 100 dB range at the midpoint, which is heard as both
sounds at once, quieter.

Measured on 48 catalog pairs (2026-09-15, CPU, a scratch script over the published route; six kinds
of sound paired within and six pairs across):

| Reading | Value |
|---|---|
| Grid blend distance at the midpoint, over the endpoint distance | median 0.005, largest 0.018 |
| Rendered midpoint fitted as a decibel blend of the rendered ends | residual 5.7 dB, fitted weight 0.50 |
| The route's own perturbation, rendered against decoded | 6.5 dB at the midpoint, 5.5 dB at the ends |
| Distance between the rendered ends | 21 dB |
| Midpoint energy over the ends' mean | 0.19–0.27 |
| Loudness at the midpoint against the ends' mean | −5.4 dB median |
| Pitch path | holds one end, then switches |

The rendered midpoint is a decibel blend down to the route's own noise, and a magnitude mix fits
almost as well. Nothing in the training asks for anything else: the linear codec is least squares
on the grid, the restorer an L1 on peak-relative decibels, and no loss reads the waveform or the
path between two sounds. A codec trained for reconstruction alone lands on the crossfade, which is
why the learned embedding that follows this work is asked for motion explicitly (the last section).

## The algorithm

`samplemorph.transport`, training-free, on each sound's own Gaussian analysis (2048/128, 1025 bins),
after Henderson and Solomon's audio transport, extended with a time map. One weight drives every
stage.

- **Onset.** `samplecore.auditory.strikes`: the local level climbing 12 dB within 20 ms starts a
  strike; the main strike is the first whose peak lies within 12 dB of the clip's peak, and the
  onset is where it first reaches its own peak minus 12 dB. The sound type reads its strikes
  through the same rule.
- **Time.** The output lasts the geometric path between the two lengths, and its onset sits at the
  interpolated share of that length. Eight frames around the onset read both sources at their own
  rate, so an attack stays single and sharp. After it, each body is read through the quantiles of
  its energy to the power of a third, gated 60 dB under the loudest frame and mixed with a quarter
  of uniform mass; the output body follows the straight line between the two sets of quantiles.
  A compressed stretch is read through a triangle as wide as the local rate.
- **Frequency, per output frame.** Both spectra are cut into groups at the minima of a smoothed
  outline between peaks at least 12 dB prominent, and each group into grains at the raw minima.
  The monotone plan pairs the groups' energy in frequency order, the optimal plan on a line for any
  convex cost. Every piece of the plan travels to the geometric point between its two group
  centers; each grain moves rigidly, read by log-quadratic interpolation, which is exact for a
  Gaussian lobe, so a partial stays a partial the phase integration can read.
- **Level.** Frame energies meet on a power mean at a third, so the path holds its loudness and a
  sound meeting silence arrives at the midpoint half as loud.
- **Phase.** Phase gradient heap integration on the transported magnitude, with no codec and no
  restorer, so both ends sound at the clean-analysis ceiling (2.7–3.0 dB held-out, against 10.8 for
  the 256-component route).

`samplemorph.transport.blend` is the control on the same analyses: both sounds read at the same
share of their lengths and blended bin by bin in decibels, the latent route's morph at the
transport's fidelity.

## The contracts

`tests/samplemorph/transport/`, on synthetic sounds, each discriminating a transport from a
crossfade:

| Contract | Transport | Blend |
|---|---|---|
| 220 → 330 Hz harmonic tones: midpoint energy on the 269 Hz series | 99.8 % | 1 % |
| Noise band 0.5–1 kHz → 2–4 kHz: midpoint energy within the 1–2 kHz band | 99.99 % | 21 % |
| Decays of 281 and 37 dB/s | 58 dB/s at the midpoint | |
| Two hits 100 ms apart | one attack | |
| Equal-level ends | within 1 dB along the path | |
| Rendered midpoint of the tones | loudest at 269 Hz | |

Symmetry, self-identity, gain invariance, chord order, continuity near the ends, silence, sounds
shorter than one transform and one-frame sounds are contracts too. A 3 s pair transports in 0.39 s
on the CPU; the phase integration is the larger cost.

**The known limit.** Balanced transport pairs partials by cumulative energy, so two tones of
different brightness split pieces off the series: 9 % of the midpoint's energy lands on the pitch
series in the synthetic probe. It is likely heard as an inharmonic haze. The remedy, unmatched
groups following the neighboring scale field, waits for the ear.

## The comparison

`samplemorph.routes` puts every way between two sounds behind one protocol: a route prepares each
end once and renders any weight. `LatentRoute` wraps the stored codec's route unchanged;
`AnalysisRoute` renders either spectral path through the phase integration.

`samplelibrary morph draw-pairs --seed S --output pairs.json` draws, from the hand labels and the
suggestions on show in the top quarter of their label's scores, two pairs within each of eight kinds
(bass drum, snare, hi-hat, bass, lead, pad, piano, chord), six pairs across kinds, one tonal and
one percussive sample heard at two rates a fifth to an octave apart, a short hit against a long
sustain, two pairs of loops, and an eight-bit low-rate sample against a sixteen-bit high-rate one.
Every sample drawn peaks at −60 dBFS or above, which leaves out the empty slots modules store as
frames of zeros; the two ends of a pair come from different modules and equivalence classes and lie
at least 6 dB apart as heard.

`samplelibrary morph compare --pairs pairs.json --output DIR [--routes …] [--blind]` renders every
pair through every route at nine weights and writes, per pair, both originals and a folder per
route holding both ends, the weights 0.25, 0.5 and 0.75, and `path.wav` (every weight in order,
150 ms apart), at the level each was rendered at. `readings.csv` holds one row per point,
`paths.csv` one per path, `verdicts.csv` waits for the ear, and `manifest.json` names the routes,
their settings or model files, and the pairs' digest. `--blind` names the route folders by letter,
the key kept in the manifest.

The readings (`samplemorph.measurement.morph_path`):

- **Endpoint fidelity.** Each end's render against the sound it renders, at matched loudness, on
  every reading of [`18-perceptual-readings.md`](18-perceptual-readings.md).
- **Blend residual.** Each point's held-out spectrum, averaged onto 64 duration-fraction columns,
  fitted as the decibel blend of the rendered ends over the cells within 60 dB of a spectrum's
  peak: the fitted weight, the residual, and the residual over the ends' distance. A crossfade
  reads near zero; the latent route read 0.28 on the 48 pairs.
- **Loudness path.** Integrated loudness per point, its offsets from the straight line between the
  ends in loudness units and in sones, and the largest dip under the first.
- **Pitch path**, on pairs of two tonal sounds at least a semitone apart: each point's heard pitch,
  its deviation from the line, and the jump share, the largest step between neighbors over the
  span, which reads 1 for a switch and 1/8 for a glide over nine weights.
- **Transposition**, on a sample heard at two rates: each point's held-out distance from the same
  sample heard at the rate between them, rendered through the same route's end.
- **Midpoint screen**, each point against the rendered ends: the peak count on a Gaussian analysis
  over the count interpolated between the ends (a dissolve reads near two), the spectral entropy
  over the wider end's, and the crest factor and the fluctuation and roughness depths over the
  values interpolated between the ends.

What the tables are expected to show on the catalog: the transport's jump share well under the
latent route's, a blend residual share far above 0.28, no loudness dip, and endpoint fidelity near
the clean-analysis ceiling. The tables screen; the ear decides.

## The gate

- **Pass:** the transport is preferred over the blend on at least four pairs spanning percussive
  and tonal material, with at most one bad example (two bad examples dismiss a method and four good ones promise it,
  [`18-perceptual-readings.md`](18-perceptual-readings.md)).
  The service then renders the transport, the latent route kept as an option.
- **An artifact of the mechanism heard twice** — ghost partials, warble, double attacks — is
  answered by a named variant rendered on the failing pairs before deciding: unmatched groups
  following the neighboring scale field, pieces tracked across frames, several onset anchors.
- **Heard as a dissolve:** the work stops and is recorded in [`06-alternatives.md`](06-alternatives.md).

## What follows

The user's aim is a self-supervised, decodable embedding whose straight lines move features. With
transport as teacher and yardstick, the next plan trains an encoder and a decoder on reconstruction,
on transposition equivariance from the same sample heard at two rates, and on interpolants distilled
toward transport midpoints, optionally judged by a realism critic; linear optimal transport,
principal components over transport maps, stands beside it as the closed-form baseline. The
comparison above takes it as one more route.
