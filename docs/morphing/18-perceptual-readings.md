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

The study itself needs listening: the user rates the reconstructions of each probe for gargle
severity and for "quieter", and every reading is rank-correlated against those labels, overall and
per sound type. The ear judged the candidate set rather than the ladder; that verdict and the
correlation table are the section "The ear's verdict on the candidate set" below.

## The night of 2026-09-11: the round trip taken apart, and a candidate fix rendered

With the ladder verdict still waiting on the ear, the night went to the one lever the numbers had
already named — the log-frequency round trip — and to a bounded check of a pretrained vocoder as a
ceiling. No training. Everything below is CPU except the ceiling, which was one GPU inference job.

### The band matrix discards half the magnitude, and its inverse was a heuristic

The forward map from Fourier bins to log-frequency bands is a fixed matrix of triangular weights,
and the way back was `np.interp` between band centers. Two facts about that matrix decide the
gargle:

| window | bands per octave | bands × bins | rank | share of the bins |
|---|---|---|---|---|
| 2048 | 144 (production) | 1355 × 1025 | 540 | **53%** |
| 2048 | 288 | 2708 × 1025 | 791 | 77% |
| 2048 | 576 | 5414 × 1025 | 1005 | 98% |
| 1024 | 144 | 1355 × 513 | 397 | 77% |
| 1024 | 288 | 2708 × 513 | 504 | 98% |
| 1024 | 576 | 5414 × 513 | 513 | 100% |

At 144 bands per octave over a 2048-point window a band at the top of the range averages forty
Fourier bins, and the matrix has rank 540 of 1025: **the production grid discards 47% of the linear
magnitude's degrees of freedom by construction.** The restored magnitude is smooth across bins where
the true one ripples, and no phase estimator can find a consistent phase for that — which is the
gargle's root cause stated exactly. No inverse recovers what the forward map threw away; the grid
sets the ceiling.

The inverse, though, was leaving fidelity on the table. On forty probes, a clean Gaussian STFT
magnitude was carried through each matrix and back by interpolation and by the least-squares inverse
of the same matrix, then made audible with PGHI (medians, against the original at the heard rate):

| window / bands | inverse | modulation distance | fluctuation excess | loudness, LU |
|---|---|---|---|---|
| 2048 clean (no round trip) | — | 0.079 | +0.0005 | −0.06 |
| 2048 / 144 | interp (production) | **0.119** | +0.0065 | **−0.37** |
| 2048 / 144 | least squares | 0.105 | +0.0021 | −0.09 |
| 2048 / 288 | least squares | 0.088 | +0.0007 | −0.07 |
| 2048 / 576 | least squares | **0.079** | +0.0006 | −0.06 |
| 1024 clean | — | 0.056 | +0.0007 | −0.03 |
| 1024 / 288 | least squares | **0.056** | +0.0007 | −0.03 |

The least-squares inverse wins on every configuration and every sound type, and with enough bands
the round trip reads *identical* to the clean rung — the corruption is gone and only the phase
estimate's own cost remains. **The least-squares inverse is now the log-frequency axis's reading
back onto the Fourier grid** (`samplemorph.canonicalizers.log_frequency.linear_axis_inverse`, cached
per geometry); on the production grid alone it cuts Griffin-Lim's flutter from +0.134 to +0.088.

Two readings from the same sweep belong beside it. The loudness loss here is −0.03 to −0.37 LU,
against the −1 to −4 LU the ladder read: the ladder's files are peak-normalized, and an estimated
phase makes a waveform *peakier* far more than it drains its energy, so at matched peak it plays
quieter. And a 1024-point window reads better for PGHI on the band round trip alone (0.056 against
0.079) — a lead the full pipeline below puts in its place.

### A pretrained mel vocoder is not a ceiling for this material

BigVGAN-v2 (44.1 kHz, 128-band mel, NVIDIA's pretrained weights, inference only) regenerated the
forty probes from its own clean mel, beside Griffin-Lim on the identical mel, read against the heard
original at 44.1 kHz:

| vocoder | held-out dB | modulation distance | flutter | roughness excess | loudness, LU | CDPAM |
|---|---|---|---|---|---|---|
| BigVGAN-v2 | 7.21 | 0.227 | +0.045 | +0.003 | −0.95 | 0.143 |
| Griffin-Lim, same mel | 8.12 | 0.275 | +0.239 | +0.024 | −0.29 | 0.120 |

BigVGAN buys its freedom from the gargle (flutter a fifth of Griffin-Lim's, roughness near zero) by
regenerating the sound wholesale from a 128-band mel — 7 dB from the original and a decibel quieter
— where the deterministic path above sits at 2.7 dB with PGHI on a clean analysis. For a pipeline
whose goal is a faithful, decodable representation, the learned regeneration is the wrong trade,
and the direction closes with numbers rather than a night of training.

### What landed

- The least-squares inverse, as above.
- The analysis window is a geometry choice (`AnalysisWindow.HANN`, the default, or `GAUSSIAN`),
  read by every analysis and inversion through `analysis_taper`, so a Gaussian analysis and the
  phase-gradient constant PGHI needs (`phase_gradient_spread`) travel with the geometry.
- **PGHI as a registered vocoder** (`samplemorph.vocoders.pghi.PghiVocoder`, `--vocoder pghi`,
  the `pghi` extra), which reads a Gaussian log-frequency analysis and refuses any other by name.

### The candidates for tomorrow, through the whole pipeline

Twelve ladder probes were rendered again at their heard rates under
`listening/candidates-2026-09-11/`, every reconstruction taken through canonicalize → restore →
vocoder — time squeeze and dynamic range included, so each file is what would ship under that
geometry — in a `peak-matched/` folder like the ladder and a `loudness-matched/` folder under one
shared headroom. Read against the original (medians over the twelve, peak-matched):

| file | geometry | loudness, LU | modulation distance | flutter | held-out dB |
|---|---|---|---|---|---|
| 2 production Griffin-Lim | Hann 2048/256, 144, least squares | −1.29 | 0.224 | +0.088 | 6.41 |
| 3 Gaussian PGHI | 2048/128, 144 | −1.06 | 0.159 | +0.028 | 6.98 |
| **4 Gaussian PGHI** | **2048/128, 288** | **−0.78** | **0.144** | **−0.020** | **4.87** |
| 5 Gaussian PGHI | 1024/64, 288 | −1.38 | 0.156 | +0.019 | 6.02 |
| 6 clean PGHI, ceiling of that analysis | 1024/64, no grid | −1.05 | 0.082 | +0.021 | 2.83 |

Through the full pipeline the 2048-point window at 288 bands per octave is the candidate on every
reading: the smallest modulation distance, a flutter on the smooth side of zero — the gargle gone
by this instrument — a decibel and a half closer in spectrum, and the least loudness lost. It costs
twice today's grid height. The 1024-point window's lead on the band round trip does not survive the
time squeeze, and it loses three LU on percussive material, so it stays a registered option.

What to listen for, in one sitting with the ladder verdict: **4 against 1** — is the gargle gone,
and is anything else lost; **4 against 2** — what the fix buys over shipping; the same pair in
`loudness-matched/` — is "quieter" still there once level is matched, or was it the peak. Severity
and "quieter" labels on these five files per probe extend `labels.csv` and the calibration study.

### The one training that fits the diagnosis: a restorer for what the grid discards

With the vocoder problem reduced to a magnitude problem, the learnable thing is the fine structure
the grid throws away: a network that reads the least-squares magnitude and predicts, from what the
corpus says such sounds carry, the structure the band averaging removed — with PGHI reading the
phase afterwards. It has a strong baseline built into its input, a supervised target for every
catalog sample, and a gate the readings can score without an ear.

The experiment (scratch, `runs/night-2026-09-11/scripts/restorer_train.py`): a two-dimensional
residual network of 0.17 M parameters over the decibel magnitude, dilations widening along
frequency (the axis the grid smoothed) to eight bins, kernels spanning neighboring frames, its
output layer initialized at zero so it starts *at* the least-squares baseline; L1 in decibels at
native resolution and two coarser poolings; 20,000 training samples from the seed-0 training split,
128-frame crops, eight epochs, ~12 minutes an epoch on the GPU. Its validation loss fell to 38%
below least squares alone. Two operational lessons on the way: a forked loader worker died of
heap corruption after ninety thousand examples (the parent held multithreaded BLAS pools at fork —
the cure is one thread everywhere before the first worker starts), and spawned workers, each
importing torch afresh, are too heavy for this machine in numbers.

On the forty validation probes the training never saw, each made audible through PGHI (medians):

| reading | clean ceiling | least squares | **restorer** |
|---|---|---|---|
| magnitude error, linear | 0 | 0.039 | **0.035** — percussive 0.071 → 0.040 |
| held-out dB | 2.95 | 4.97 | **4.40** — tonal 4.82 → 3.93 |
| modulation distance | 0.083 | 0.135 | **0.110** — percussive 0.220 → 0.138 |
| loudness, LU | −0.02 | −0.15 | **−0.035** — percussive −0.43 → −0.035 |
| fluctuation excess | +0.0003 | −0.0024 | +0.0012 |
| flutter, the old screen | −0.002 | −0.014 | +0.012 |

The learned prior recovers about a third of what the grid discards on spectrum, a third of the
percussive modulation deviation, and nearly all of the percussive energy loss. The one reading that
moves the other way is the old flutter screen: the restorer adds ripple, and some of it is ripple
the reference does not have — the principled fluctuation reading sits at the clean level. Its
reconstruction is the seventh file in every candidate folder (`7_gauss2048_288_restored_pghi`), so
tomorrow's sitting hears it beside candidate 4. It lands in the repository as a vocoder with a
training command of its own only if the ear agrees with the numbers.

## The ear's verdict on the candidate set (2026-09-11)

The user listened to the `loudness-matched/` folder and judged it the fair stage; the peak-matched
folder was set aside as unbalanced, and one probe (`tonal_f39948450418`) as too close to call. The
words are kept verbatim in `listening/candidates-2026-09-11/verdicts.md`. For the study, `labels.csv`
codes every file of the eleven judged probes 0–3 — 0 in the indistinguishable group or praised, 1 a
subtle remark that still passes, 2 a named artifact or a lost feature, 3 a plain failure — plus
"louder" or "quieter" where the ear said so. The coding is ours, from the prose, and two readings of
it are inferences: on the riser `c110ba83c95f`, "6–7 pass the quality bar" is taken to place files
2–4 below it; on `1884be2a55e2`, the files the ear did not mention (3–5) are coded 0.

### Each variant under the house rule

Two bad examples dismiss a method; four good ones promise it.

| file | geometry | fails (2–3) | subtle (1) | reading |
|---|---|---|---|---|
| 2 production Griffin-Lim | Hann 2048/256, 144 | 6 of 11 | 0 | dismissed: "not that bad after all, but it does not pass the quality bar" |
| 3 Gaussian PGHI | 2048/128, 144 | 2 | 2 | dismissed |
| 4 Gaussian PGHI | 2048/128, 288 | 2 | 1 | dismissed on its own: the slap-bass transient (`72bc`) and the riser (`c110`) |
| 5 Gaussian PGHI | 1024/64, 288 | 2 | 2 | dismissed; the riser's strongest flanger |
| 6 clean PGHI, no grid | 1024/64 | 1 | 2 | the ceiling holds; PGHI on its own can chorus (`1884`) |
| **7 restorer + PGHI** | **2048/128, 288** | **0** | **3** | **the only variant with no bad example** |

The restorer is the one grid-based variant that keeps the slap-bass transient and passes the riser —
the two probes where candidate 4 fails — and its three subtle remarks are "loses a little but still
very faithful" (`a5f4`), "a little flanger but good" (`1884`) and "noticeably quieter" (`1ce0`).
Candidate 4's two failures are exactly what the restorer was trained to put back, and the ear's
ordering matches the numbers' (held-out 4.97 → 4.40 dB, percussive modulation distance 0.220 → 0.138).

### Where the readings agree with the ear, and where they do not

Within-probe pairwise concordance — over every pair of files of one probe the ear ranked differently,
the share the reading orders the same way — and Spearman ρ against severity, per sound-type tag:

| reading | all pairs | other | percussive | tonal | ρ other | ρ percussive | ρ tonal |
|---|---|---|---|---|---|---|---|
| \|fluctuation excess\| | 44/66 | 7/22 | **16/17** | **21/27** | −0.07 | **+0.74** | **+0.57** |
| modulation distance | 42/66 | 7/22 | 14/17 | 21/27 | −0.13 | +0.73 | +0.23 |
| \|roughness excess\| | 40/66 | 8/22 | 14/17 | 18/27 | −0.21 | +0.65 | +0.39 |
| held-out dB | 41/66 | 8/22 | 12/17 | 21/27 | +0.07 | +0.34 | +0.46 |
| the old flutter screen | 37/66 | 7/22 | 11/17 | 19/27 | +0.05 | +0.18 | +0.47 |
| lower peak at matched loudness | 41/66 | 10/22 | **17/17** | 14/27 | −0.11 | +0.30 | +0.01 |

- **On percussive and tonal material the fluctuation reading tracks the ear.** The slap-bass
  transient loss reads as erased fluctuation and roughness (−0.02 to −0.03 on files 2–5, within
  0.008 of zero on 6 and 7); the riser's flanger reads as erased fluctuation in the ear's order (file
  5 at −0.039, files 3–4 at −0.015, file 7 at +0.005). The plan's adoption bar (|ρ| ≥ 0.6, right sign)
  is met on percussive material and approached on tonal.
- **A lower peak at matched loudness is the best percussive reading of all** (17 of 17 pairs). At
  equal loudness, a lower crest factor is a smeared transient. That is the crest-factor reading in
  its natural form, and it costs nothing.
- **On the "other" tag every reading is below chance** (7–10 of 22 pairs). Two causes are visible.
  A chorus (file 6 on `1884`) is invisible to the envelope readings — a spectral sweep near 1 Hz sits
  under the fluctuation lobe's lower edge — while the same probe's files 3–5 read as the most erased
  modulation in the whole set (fluctuation −0.04, the old screen −0.15) and the ear passed over them.
  On the kick loop `a5f4` the ear prized Griffin-Lim's transient prominence where every reading
  charges it for the gargle it adds (the old screen +0.126). Erased modulation is heard on a riser and
  a slap bass and forgiven on a loop; the readings cannot yet tell which.
- **Level.** At matched BS.1770 loudness the ear still called five files louder or quieter — files 3,
  6 and 7 on three probes, each a file with more fine structure than candidate 4. The meter reads all
  five at 0.00 LU and no headroom clamp touched them (the clamp held one file in the set, `1884`'s
  file 7, 1.76 LU under; the ear called that one good). On the kick `1ce0` every reconstruction at
  matched *peak* reads 7–10 LU under the original: a saturated, flat-topped original against a
  reconstruction whose onset overshoot sets the peak. That is what "quieter" was in the first ladder,
  and why the loudness-matched stage is the fair one.

### What the verdict decides

- **Production Griffin-Lim is dismissed by ear** (six of eleven probes), which closes the ladder
  verdict it stood in for. The path that passes — a Gaussian analysis, the least-squares reading back,
  the restorer, PGHI — needs no trained phase model, so the modulation-domain loss on the phase model
  (the plan's Phase 7) is moot.
- **The representation fix alone is not enough.** Candidate 4 fails two probes on lost fine
  structure; the restorer recovers both with no bad example of its own. Adopting the geometry means
  adopting the restorer with it.
- **Readings adopted:** the loudness delta (already); |fluctuation excess| as the screen on tonal and
  percussive material; the peak at matched loudness for percussive transients; the unsigned
  modulation distance as the ordering instrument on percussive material. No reading is trusted on the
  "other" tag, where a chorus goes unseen.
- **Comparison moves to matched loudness.** Rendering already offers it; `held_out_spectrum`'s peak
  normalization is the Phase 8 row this closes, since it charged a saturated kick 7 LU of overshoot.

### What landed on the verdict (2026-09-11)

The user adopted the path: "the most promising solution, from all we've got so far", with the
note that this restorer is free to learn the library it serves rather than sounds in general. Four
commits (`6bee2fe`, `5d84477`, `bad9143`, and the write-up):

- **The production geometry is the Gaussian analysis at 288 bands per octave**, hop a sixteenth of
  the 2048-point window (`DEFAULT_BINS_PER_OCTAVE`, `DEFAULT_ANALYSIS_WINDOW`,
  `DEFAULT_LOG_FREQUENCY_HOP_LENGTH`), PGHI the estimated-phase rung of every reconstruction table,
  `pghipy` part of the `morph` extra. Two corrections found on the way: the rank table above is right
  and the night's memory of it was not -- 288 bands keep 77% of the bins, the deficit sitting in the
  top analysis octave (288 bands for 512 bins), which at the usual playback rate is heard at 2–4 kHz
  and is exactly what the restorer puts back; and numpy's default pseudo-inverse cutoff inverted
  singular values near machine precision into entries of order 10¹³ -- neutral on real material
  (measured on three probes to the fourth decimal) but now cut at 10⁻⁶ of the largest, so the inverse
  is of the order of the weights and a bin no band touches reads exactly silent.
- **The restorer is a vocoder** (`samplemorph.vocoders.restored.RestoredPghiVocoder`, `--vocoder
  restored`, the default): the least-squares reading, compressed to decibels over the grid's own
  dynamic range, through the network (`samplemorph.vocoders.restorer_model.Restorer`), expanded, and
  integrated. It refuses a spectrogram from another analysis by name and reads either anchor. The
  integration itself now holds every magnitude at the grid's dynamic range below its peak, since
  pghipy differentiates the log magnitude and an exact zero next to a loud bin handed it a garbage
  gradient; measured neutral at −100 dB on all twelve probes (`pghi_floor_check.py`), and it is what
  makes an untrained restorer read exactly as PGHI alone, which is a test.
- **`train-restorer`** teaches it on the whole catalog by default (every sample within the probe
  bounds), through the same derived-example machinery as `train-phase`, now shared: one
  `AnalysisCorpus` and `AnalysisDataModule`, one `DerivedExampleSet` a family parameterizes with how
  it derives and crops, one `pipeline_analysis` that carries a waveform through the grid and pairs it
  with its own analysis, one settings type and one command body. The validation log carries the
  least-squares baseline beside the loss, so an epoch reads as an improvement only under it.
- **The night's checkpoint is the stored restorer** (`models/restorer.pt`, converted by
  `convert_restorer.py` with its layers renamed and its log recorded in the description). Through the
  landed vocoder it reproduces file 7 of the candidate set on all twelve probes: every reading within
  a few hundredths, waveform correlation above 0.98 on ten, and on two a polarity or island-phase
  choice inside the integration that carries no sound (`landed_path_check.py`).

Open, and heavy: the restorer retrained on the whole catalog (the stored one saw 20,000 samples), the
grid caches rebuilt on the new geometry (twice the height), and the descriptor and codec chain after
them. Registered for later, at the user's request: a light alignment between the morph
representation and the hand labels, in either direction, once morphing itself is solved; and a
guard that a morph is more than a convex blend of its endpoints -- a reading that compares the
midpoint's grid with the mean of the two endpoint grids, so a codec that had learned to crossfade
would be caught by a number before an ear.

## How to re-derive any of this

`runs/night-2026-09-10/scripts/ladder_measure.py` (beside the library, outside the repository)
reads the rendered set and writes `listening/ladder-2026-09-10/metrics.csv`; the readings it calls
are `samplemorph.measurement.loudness`, `samplemorph.measurement.modulation_spectrum` and
`samplecore.auditory.sound_type`, committed and tested. The keyword calibration is
`sound_type_calibration.py` in the same folder, a read-only draw of seed 11. The night's sweep is
`runs/night-2026-09-11/scripts/roundtrip_sweep.py` (`roundtrip_sweep.csv`), the ceiling
`bigvgan_ceiling.py` (`bigvgan_ceiling.csv`, the model cloned beside it), and the candidate set
`candidates_listen.py` with the restorer's file added by `candidates_restored.py`. The restorer is
`restorer_train.py` (checkpoint `restorer_final.pt`, log `restorer_train.log`) and its held-out
readings `restorer_evaluate.py`. The verdict study is `candidates_measure.py`, which writes
`listening/candidates-2026-09-11/metrics.csv` for both matchings, and `calibration_study.py`, which
joins it with `labels.csv` and prints every table of the verdict section. After the verdict:
`pghi_floor_check.py` (the integration floor), `convert_restorer.py` (the checkpoint into the
store) and `landed_path_check.py` (the landed vocoder against file 7).
