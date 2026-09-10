# Scoring and evaluating: directions to choose

Listening is ahead of the numbers, and the numbers have misled us more than once: the canonical grid
distance and every phase-gradient reading tie Griffin-Lim with the learned models where the ear hears
a wide gap ([`12-learned-vocoder.md`](12-learned-vocoder.md)), and CDPAM — adopted as a learned
oracle — ranks below chance per probe and over-penalizes phase (the Stage 2 verdict, recorded in the
flutter memory). Before another run spends a night, this document settles two questions that are
easy to conflate and are in fact different jobs:

- **Evaluating** — which *numbers we trust* to stand in for the ear. A metric may be
  non-differentiable, slow, or external; it only has to correlate with listening.
- **Scoring** — which *objective a model minimizes*. A loss must be differentiable, stable under a
  gradient, and cheap enough to run every step.

Each half below is a menu with the trade-offs made explicit, and each ends in **directions to
choose** — the forks to decide before starting. The whole document is desk work: it names
experiments, it runs none. Every heavy run still waits for the green light and, right now, for the
listening verdict on the representation ladder (the blocker recorded in the plan).

## The shape of the defect, which sorts both menus

The three surveys behind this document agree on one physical picture, and it is what makes most
off-the-shelf instruments the wrong tool.

The gargle is a **structured phase error that holds the magnitude fixed**. Magnitude is exactly what
Griffin-Lim and the learned phase model hold constant, so a metric that reads only magnitude reads
the same number for two reconstructions that sound entirely different — this is the blindness
[`12-learned-vocoder.md`](12-learned-vocoder.md) already measured. At the other extreme, a
waveform-domain or raw-phase metric charges for a **global phase offset that no listener hears** (a
frequency-independent shift moves every sample yet is inaudible — the same fact the phase model's
"delay a crop cannot know about" correction turns on). CDPAM's contrastive time-domain embedding sits
near that extreme, which is the *predicted* reason it ranks below chance for us, rather than a bug in
our harness.

The audible part is real and lives in the **temporal-modulation domain**. A slowly moving comb
sweeps its notches across the spectrum, so many subbands share a time-varying gain ripple. That
ripple straddles two neighboring psychoacoustic axes:

| Axis | Modulation-rate band | Peak sensitivity | Percept |
|---|---|---|---|
| **Fluctuation strength** | below ~20 Hz | ~4 Hz | warble, flutter, "wavering" |
| **Roughness** | ~15–300 Hz | ~70 Hz | buzz, "metallic," gargle |

Its *cause* is loss of **vertical phase coherence** across the several bins of one partial — what
Laroche & Dolson (1999) named *phasiness*. Structured group-delay errors of this kind become audible
at well under a millisecond (Liski et al. 2021), so the effect is small in the waveform and loud in
the ear.

Two consequences run through everything below:

1. **The right instrument is sensitive to *structured, local* phase roughness and invariant to
   *global* phase offset.** Magnitude-only reads too little; raw-waveform reads too much. The
   middle ground is an **auditory / modulation-domain** representation.
2. **The two failure signs are two different defects.** Griffin-Lim's `modulation_excess` of **+0.10**
   is *added* modulation — real roughness, the classic comb. The learned models' **−0.13** is
   *erased* micro-modulation — an over-smoothed, "dead" reconstruction, not a gargle. A single signed
   number conflates "buzzy" and "dull," so every reading and every loss here reports a **signed** value
   (which side) alongside an **unsigned** one (how far).

## What we already have

**Evaluating**, in `samplemorph.measurement`:

| Module | Reads | Sensitive to the gargle? |
|---|---|---|
| `reconstruction.py` | log-mel RMSE | no — magnitude only |
| `comparison.py` | log-magnitude grid distance (dB) | no — magnitude only |
| `equivariance.py` | transposition retrieval / retuning | measures the descriptor, not quality |
| `plausibility.py` | morph-path monotonicity, energy, spread | measures the morph, not quality |
| `phase_quality.py` | `modulation_excess` (signed frame-to-frame flutter) | **partly** — a fluctuation-lobe screen; its frame-rate envelope stops short of roughness |
| `perceptual_distance.py` | CDPAM (learned, full-reference) | over-penalizes phase; below chance per probe |
| `modulation_spectrum.py` | `fluctuation_excess`, `roughness_excess` (signed), `distance` — through the `samplecore.auditory` gammatone front end at the heard rate | **yes, on both lobes** — the principled form of the flutter screen |
| `loudness.py` | `delta_lu` — BS.1770 K-weighted integrated loudness, reconstruction minus reference | measures level, the axis every shape reading normalizes away |

**Scoring**, in `samplemorph.training`:

| Term | Form | Property |
|---|---|---|
| `phase_gradient_error` | phase-advance error over time and frequency, loudness-weighted, read through the conjugate so nothing unwraps | phase-aware |
| `multi_resolution_spectral_error` | L1 of log-magnitude through windows 512 / 1024 / 2048, Hann | magnitude only |
| `reconstruction_error` (codec) | mean absolute error over the grid and two coarser poolings | over-smooths |
| `prior_divergence` (codec) | divergence to the unit Gaussian | buys interpolability |
| `cycle_error` (codec) | cosine to the descriptor it decoded from | makes the decoder use its conditioning |

The descriptor's own contrastive objective lives in [`14-learned-descriptor.md`](14-learned-descriptor.md).
So the scoring side already carries a phase-aware gradient term and a multi-resolution magnitude term;
the evaluating side already carries a flutter screen and a learned distance. The menus below name what
is *missing* against the literature, not what to rebuild.

## Evaluating: the metric menu

**The governing finding is a Goldilocks gap: no off-the-shelf metric is validated to track
metallic/gargle phase-inversion artifacts on short lo-fi music.** The meta-evaluation literature is
unanimous that a metric's correlation with listening is content-dependent and does not transfer
off-domain — ViSQOL-audio reads Pearson 0.81 against music-codec listening tests and 0.41–0.48
against speech (Chinen 2020; the Zimtohrli 2025 benchmark), and objective metrics have been shown to
contradict listener preference outright on music synthesis (Vinay & Lerch 2022). So the rule that
governed this project from the start holds here too: **listening is ground truth, a metric is a
screen, and a metric earns trust only after it correlates with our own hand labels** (the
"render before adopting" and "two bad examples dismiss a method" memories).

One structural advantage shapes the choice: we hold **paired reference↔reconstruction** samples, so
per-sample full-reference metrics apply directly, and a distribution metric like FAD — which discards
the pairing — is only ever a corpus-level guard.

| Metric | Type | Rate | pip + license | CPU | Music-alignment evidence | Caveat for us |
|---|---|---|---|---|---|---|
| **ViSQOL v3 (audio)** | full-ref, NSIM on a gammatone spectrogram | 48 kHz | `visqol-python`, Apache-2.0, active | yes | best classical metric on music (Pearson 0.81, USAC MUSHRA) | wants 3–10 s clips; our ~0.7 s low-rate samples stress its patch model |
| **Audiobox-Aesthetics (PQ)** | no-ref, aesthetic axes | 16 kHz mono | `audiobox_aesthetics`, weights CC-BY-4.0 | yes | the only *music-trained* learned predictor (music PQ Pearson 0.887) | trained on 10–30 s; use as a **reconstruction−original delta** to cancel the lo-fi baseline |
| **Zimtohrli** | full-ref, auditory model | 48 kHz | Apache-2.0 (Google) | yes | avg Pearson ~0.68, competitive with POLQA | newer, unproven on lo-fi; use as a second auditory opinion |
| **FAD-CLAP** | distribution (no pairing) | embedding-set | `fadtk`, MIT | yes (cache embeddings) | CLAP embedding best for music; detects Griffin-Lim/mel artifacts in aggregate | **corpus-level only**; never VGGish (≈ chance on non-speech) |
| **CDPAM** | full-ref, learned | 22.05 kHz mono | `cdpam`, MIT (in the repo) | yes | strong on speech; over-penalizes phase | demote from oracle to one input in the calibration study |
| **Modulation-spectrum distance** | full-ref, interpretable (build it) | native | — (self-implement) | yes | the principled form of our flutter screen | the bespoke instrument; design below |
| **Loudness (K-weighted)** | full-ref delta | native (≥0.4 s) | `pyloudnorm`, MIT | yes | the missing axis — reads energy, not the gargle | short-sample gating → RMS-dBFS fallback below 0.4 s |

Demoted or set aside, with the reason: **any magnitude-only distance** as the ranker (blind by
construction); **speech MOS predictors** — SQUIM, UTMOS, DNSMOS, NISQA (their axes are undefined for
music, and NISQA's weights are non-commercial); **PEAQ** (GPL, non-conforming build, weak fixed
mapping); **PEMO-Q** and the **2f-model** (licensed / not distributable, though the 2f-model is the
best cross-domain generalizer in the literature and worth watching); **DPAM** (TensorFlow 1.x, a poor
neighbor to torch 2.9). **FAD for per-sample verdicts** is structurally impossible — it throws away
our strongest signal, the pairing.

### Loudness, the axis the panel was missing

Every metric above judges spectral shape or modulation, and none of them reads absolute level — the
canonical reconstruction distance actively removes it, since `held_out_spectrum` peak-normalizes both
waveforms before comparing (`comparison.py`), so a reconstruction that returns quieter reads the same
distance as one that keeps its level. Listening caught exactly this: a reconstruction can come back
with audibly less energy. The representation is not the source — the grid carries level out as
`log_gain` and restores it (`common.py`) — so the loss is a **synthesis** effect (Griffin-Lim's
inconsistent-phase projection and the learned models' erased micro-modulation each cost energy and
presence), sitting downstream of where the gain is preserved and invisible to a peak-normalized
metric.

The reading that closes the gap is **ITU-R BS.1770 integrated loudness (LUFS)**, whose K-weighting is
a high-pass near 38 Hz plus a presence shelf applied *before* the energy is summed — the calibrated
form of "high-pass so inaudible low frequencies do not inflate the number." Report it as a signed
reconstruction−reference delta in LU, the sign saying whether the reconstruction gained or lost
loudness. `pyloudnorm` (MIT) implements it. Two design points, both taken from the OptiSample pipeline,
whose ingest already does this:

- **Short samples fall below BS.1770's gating block.** OptiSample falls back to plain RMS-dBFS below
  0.4 s (`metrics/preprocess.py`); our median sample is ~0.7 s but many are shorter, so the reading
  needs the same momentary / ungated fallback.
- **Match, then report the delta.** OptiSample loudness-normalizes both signals to a fixed target
  before its spectral comparison and reports the loudness delta as a separate diagnostic. That is the
  pattern to copy — level-match for the shape metrics so a quiet reconstruction is not charged twice,
  and report the loudness delta as its own reading.

One debugging lead for the energy loss itself: a synthesis that returns quiet often traces to a
missing synthesis-window normalization or a non-COLA hop, so the vocoder's overlap-add is the first
thing to verify before attributing the loss to phase.

**A pipeline high-pass, registered as the canonicalizer's call.** The un-weighted-energy trap is real:
a broadband `mean(x²)`, or any analysis with `fmin = 0`, lets sub-audible rumble and DC dominate the
number (OptiSample weights energy only by a scalar exponent and runs its mel analysis at `fmin = 0`,
so it inherits the trap on the analysis side even while high-passing the audio). Our canonicalizer
removes DC (`prepare_mono`) and nothing more. A gentle high-pass on the audio — OptiSample uses a
**solved-order zero-phase Butterworth at 30 Hz**, 60 dB down by 10 Hz (`dsp/subsonic.py`), at ingest
"so every later stage sees the content a listener has" — is reasonable hygiene, and may ease two
problems [`09-measurements.md`](09-measurements.md) already names: bass bands starved of Fourier
resolution, and the alignment anchor pulled by low-frequency energy. It moves the canonicalizer's
grid, so it is a **representation change** — registered here, gated on hearing that it does not thin
out kicks and basses, rather than folded in. It is unlikely to be the cure for the energy loss (a
synthesis effect); its payoff is honest energy measurement and cleaner bass geometry.

**The calibration study is the gate, and it is the one experiment this half proposes.** Hand-label a
few dozen probes for gargle severity (or rank them), render each candidate reconstruction, and compute
the rank correlation (Spearman / Kendall) of every metric against those labels. The metric that
correlates is the one adopted; the rest are recorded as findings. This is the same staged shape the
plan already uses for CDPAM, widened to the panel above. `VERSA` (an OSS toolkit bundling ~65 metrics
under one API) is a practical way to run several external metrics for the study without wiring each by
hand, kept ephemeral like the `pghipy` experiments.

### Directions to choose — evaluating

- **E1 — external auditory panel.** Adopt ViSQOL-audio + Audiobox-PQ-delta + Zimtohrli as a
  three-metric screen, each an independent auditory representation so disagreement between them is
  itself a signal. Cost: three dependencies, a fixed working rate and padding to reach their minimum
  clip length. *Recommended as the breadth option.*
- **E2 — the bespoke modulation-spectrum distance only.** Build the interpretable metric below as the
  primary evaluator, no external dependency, tuned to our exact defect and our rates. Cost: it is new
  code to validate, and it is one instrument rather than a panel. *Recommended as the depth option.*
- **E3 — both.** External panel as the screen, the modulation-spectrum distance as the interpretable
  explanation of *why* — the division of labor the plan already names for CDPAM-vs-flutter, made
  honest. *Recommended overall; E2 is the load-bearing half and shares its build with scoring.*
- **E-corpus — FAD-CLAP as a regression guard.** Optional add to any of the above: one corpus-level
  number that whole-batch reconstructions are not drifting from whole-batch originals in CLAP space.
- **E-loudness — a K-weighted loudness delta.** Add to any panel: a cheap, interpretable BS.1770
  reading (signed reconstruction−reference LU) that is the only instrument catching a reconstruction
  that returns quiet — the effect listening flagged that every shape metric normalizes away. Belongs
  in the calibration study alongside the rest.

## Scoring: the loss menu

Two defects need two tools, and no single loss fixes both. Magnitude and mel losses are the stable
**scaffold**; the **cure** for each defect is a different, more specialized term layered on top.

| Loss | Targets | Differentiable / stable | pip + license | Phase-aware | Over-smoothing | Fit |
|---|---|---|---|---|---|---|
| **Multi-resolution STFT** | magnitude at several resolutions | yes, very stable | `auraloss`, Apache-2.0 | no | mitigates, cures neither | the better magnitude floor (we have a hand-rolled version already) |
| **Mel / log-mel L1** (multi-window) | auditory-scaled magnitude | yes, stable | DAC / EnCodec / BigVGAN, MIT | no | causes when alone | good auxiliary; DAC's multi-window recipe fills HF holes |
| **Perceptual weighting** (A-/mel-weight) | error where the ear is sensitive | yes | `auraloss` (`perceptual_weighting`) | no | neutral→mitigates | a knob on the floor; **A-weighting de-emphasizes the HF that defines lo-fi brightness — A/B it** |
| **Anti-wrapping phase** (IP / GD / IAF) | correct phase and its derivatives | yes, stable | self-implement (~3 lines) | **yes — the only truly phase-aware family** | neutral | the principled cure for the gargle; needs a *learned, differentiable* phase predictor to wrap |
| **Modulation-domain / envelope** | subband amplitude-modulation = the flutter axis | yes | self-implement | no (envelope-domain) | cures spurious modulation | targets the gargle directly, on the magnitude grid, **no vocoder needed** |
| **Adversarial + feature-matching** | realistic fine structure | differentiable, least stable | reuse pretrained DAC / BigVGAN discriminator, MIT | indirectly | **the definitive cure for over-smoothing** | strongest and most expensive; reuse a frozen discriminator to avoid cold start |
| **CDPAM as a loss** | learned perceptual distance | yes, stable | `cdpam`, MIT | yes (waveform) | adds detail | full-reference, so low reward-hacking risk; add after L1+MR-STFT, then finetune |
| **SI-SDR / time-domain** | sample-level fidelity | yes | `torchmetrics` | needs sample-aligned reference | blind to flutter | **poor fit** — a magnitude-first morph has no sample-aligned target |

A caution the literature is explicit about: **optimizing a no-reference quality predictor invites
reward-hacking** — an optimized NR MOS model hallucinated an audible tone (Close et al. 2024). Losses
here are full-reference or structural for that reason; the no-reference predictors above stay on the
*evaluating* side, never the scoring side.

### Directions to choose — scoring (cheapest first)

- **S1 — floor swap.** Replace the codec's mean-absolute-error term with `auraloss`
  multi-resolution STFT (and consider its random-resolution variant), matching the phase model's
  existing multi-resolution term. A better magnitude objective; it cures neither defect but is the
  scaffold the rest layer onto. *Cheapest; do first.*
- **S2 — modulation-domain envelope loss.** A penalty on subband envelope-modulation spectra targets
  the gargle directly, is phase-blind and alignment-tolerant, runs on the magnitude grid with no
  vocoder, and shares its whole front-end with the modulation-spectrum *metric* (E2). *Cheapest
  defect-specific win; highest leverage because one build serves both axes.*
- **S3 — anti-wrapping phase loss.** Once phase reconstruction is a learned differentiable predictor
  (a Vocos-style complex-STFT head is the natural host), add instantaneous-phase, group-delay and
  instantaneous-frequency terms through the anti-wrapping function. The principled cure for
  phase-origin gargle, and the family most aligned with our defect. *Blocked on a differentiable phase
  predictor — it will not wrap around Griffin-Lim.*
- **S4 — adversarial + feature-matching.** Reuse a pretrained DAC or BigVGAN discriminator as an
  off-the-shelf adversarial + feature-matching term on rendered audio. The community-standard cure for
  the over-smoothing the codec's regression loss produces. *Most expensive; expect learning-rate and
  warm-up care; keep the magnitude term for stability.*
- **S5 — CDPAM as an added term.** `L1 + MR-STFT` first, then finetune on CDPAM (the recipe that
  scored highest in its paper). Full-reference, so it resists reward-hacking, and it is reported to
  improve pitch tracking — aligned with the fundamental-anchor work ([`16-pitch-anchor.md`](16-pitch-anchor.md)).

## The modulation-spectrum distance — the bridge between the two menus

One build serves both columns: as a **metric** it is the interpretable, signed reading that explains a
score (E2); in **differentiable** form it is the gargle-killing loss (S2). It is the principled version
of `phase_quality.modulation_excess`, and the psychoacoustic survey gives concrete design parameters,
each with a citation:

- **Front end:** a gammatone / ERB filterbank of ~24 channels (the SRMR and Dau-model front end;
  Falk et al. 2010), which our log-frequency grid maps onto naturally.
- **Envelope:** the Hilbert envelope per channel, through a compressive (~cube-root) nonlinearity so
  the measure lives in a perceptual amplitude domain (Zwicker specific loudness), windowed at ~200 ms
  (Daniel & Weber 1997).
- **Modulation weighting:** weight the per-channel modulation spectrum across **two lobes** — a
  fluctuation lobe ~1–20 Hz peaking at 4 Hz, and a roughness lobe ~20–150 Hz peaking at 70 Hz —
  rolling off below ~1 Hz and above ~150–300 Hz. SRMR's 8 log-spaced modulation bands (4–128 Hz) are a
  ready-made grid that brackets both.
- **Loudness weighting and an audibility floor:** weight each band's contribution by its energy (as
  `phase_quality` already weights bins) and soft-threshold modulation depths below ~0.05, which is the
  detection floor (Viemeister 1979).
- **Distance:** the loudness-weighted L1 over the two lobes, reported **signed** (added roughness vs
  erased micro-modulation) and **unsigned** (magnitude of the deviation).

**One correction to carry into the build:** to reach the 70 Hz roughness peak the envelope needs a
Nyquist above ~150 Hz, so the envelopes must be read from the **time-domain reconstruction through the
gammatone bank**, not from re-analyzed STFT frame magnitudes. The current `modulation_excess`, read
from restored-grid frames, may be sampling only the fluctuation lobe and missing roughness — worth
verifying against the frame rate it actually uses before the signed reading is trusted on the
roughness axis.

If, later, separating a *comb* (a fixed spectral periodicity) from *diffuse* roughness matters — for
attributing a bad score to phasiness (the cause) versus added roughness (the symptom) — the
Chi–Ru–Shamma (2005) spectro-temporal-modulation model (rate × scale) is the representation where a
comb concentrates at a specific scale. That is a later refinement, not the first build.

## Decision points, collected

The forks to settle before any run, with a recommendation for each:

1. **Evaluating breadth vs depth.** → **E3** (external panel as screen + bespoke distance as
   explanation), because E2 is the load-bearing half and shares its build with S2.
2. **Which loss first.** → **S1 then S2**: swap in the multi-resolution STFT floor, then add the
   modulation-domain envelope loss that reuses the E2 front end.
3. **When to touch phase (S3) and over-smoothing (S4).** → after a differentiable phase predictor
   exists (S3) and after the codec's smoothing is confirmed audible by listening (S4) — both gated on
   the representation-fix decision the ladder verdict feeds.
4. **CDPAM's role.** → **evaluate-only for now**, one input in the calibration study, and an S5 loss
   term only once the representation is clean.

## Sequencing against the listening gate

This document is the menu, not the meal. The single build that pays into both columns — the
modulation-spectrum front end (E2 + S2) — is CPU-only and needs no listening to *write and unit-test*
(a tone with injected 6 Hz AM reads positive; a steady tone reads near zero). But which **direction**
to commit to is downstream of the ladder verdict recorded in the plan: if PGHI-on-clean is transparent
and the gargle enters at the log-frequency round trip, the representation fix leads and the phase-loss
directions (S3) recede; if the time-squeeze is heard to cost percussive transients, that reopens the
grid width as a variable. The calibration study (the evaluating gate) and the modulation-spectrum build
are the two pieces of work that can start the moment the ear has spoken.
