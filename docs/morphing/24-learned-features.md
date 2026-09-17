# A representation whose straight lines move features

The morphs built so far ([`20-audio-transport.md`](20-audio-transport.md),
[`21-partials.md`](21-partials.md), [`23-envelope.md`](23-envelope.md)) were designed by hand, and
each one moves some features and dissolves others. The longer aim has always been a *learned*
representation: an embedding that describes a sound for the cloud and decodes back to audio, whose
straight lines move features. This document reads the literature that bears on one question and
draws a plan from it:

> How can an embedding be trained, without labels, so that its coordinates carry *where* things
> are (a pitch, a resonance, a decay) rather than *which spectrogram bin is lit*, so that a convex
> combination of two sounds moves things instead of crossfading them?

The reading covered three areas: classical and optimal-transport morphing and how morphs are
judged; pitch–timbre disentanglement and timbre transfer; self-supervised audio representations
and what their coordinates encode. About sixty papers were read, most in full text; the sources
are listed at the end, with the ones that could only be read second-hand marked.

## Why the question has this shape

A latent whose decoder is affine in the decibel spectrogram interpolates as a decibel crossfade,
whatever the encoder learned: the decoded midpoint is the average of the two decoded ends, bin by
bin. That is a theorem about the decoder, and it is why the grid codec's straight lines dissolve
([`20-audio-transport.md`](20-audio-transport.md)). For a straight line to move a feature, the
decoder must be nonlinear in a coordinate that stands for the feature's *position*, and the
training must have put the position into that coordinate. Every result below is about how that
happens or fails to happen.

## What the literature says

### A morph moves positions; everything at a fixed coordinate dissolves

Every representation in the classical literature that morphed rather than dissolved is a set of
position coordinates: partial frequencies (Tellman, Haken and Holloway 1995; Fitz et al. 2002;
Kazazis, Depalle and McAdams 2016), a warp of the excitation's frequency axis along a pitch track
(Slaney, Covell and Lassiter 1996), line spectral frequencies for resonances (Paliwal 1995; Islam
2000), a flow field over the spectral envelope (Ezzat et al. 2005), and the displacement of
spectral mass under optimal transport (Henderson and Solomon 2019; Roma, Green and Tremblay 2020;
Valdivia et al. 2025). Anything interpolated as an amplitude at a fixed coordinate crossfades.

The two-pitch-content midpoint that ended the partials route is the oldest named failure in the
field. Slaney, Covell and Lassiter (1996) show a crossfade of two vowels at different pitches and
write that the morph "has two separate pitches, causing the sound to be perceived as two different
auditory objects, and destroying the illusion of a continuous morph". Their remedy is the split
the envelope route now uses, a smooth spectrogram times a fine-structure spectrogram, with one
more step: the fine structure's frequency axis is stretched along a single pitch track so the
pitch peaks agree, and only then crossfaded, while the smooth spectrogram is crossfaded as it is.
Pitch moves as a position; the envelope dissolves. Their method knows one pitch track per sound
and says nothing about chords.

The transport's warble on chords is likewise named by its inventors. Henderson and Solomon (2019)
state that their per-frame plans do "not guarantee temporal consistency between transport maps",
so "a pair of wavering orchestral chords can produce a fluctuating pitch". The published fixes
compute the correspondence once per pair: Roma, Green and Tremblay (2020) factor each sound into
spectral templates by non-negative matrix factorization, pair the templates once by assignment on
a Wasserstein cost, and move each pair by one displacement plan; Valdivia et al. (2025) solve one
unbalanced transport over the whole time–frequency plane with a penalty on displacement in time,
which keeps onsets in place. Both report examples rather than measurements.

Where a feature has no partner, four strategies are documented: a phantom partner at the harmonic
position with zero amplitude, so the orphan glides and fades (Tellman, Haken and Holloway 1995);
fading in place, which Kazazis, Depalle and McAdams (2016) report causes no stream segregation
for sounds at the same fundamental; forced pairing by mass conservation, which Henderson and
Solomon find dips the level near the ends whenever a bright sound meets a dark one; and unbalanced
transport, which lets mass appear and vanish at a price (Valdivia et al. 2025).

### The envelope crossfades its resonances too

The envelope route interpolates a cepstral envelope in decibels. Caetano and Rodet (2013) compared
envelope parameterizations on 26 pairs of instrument notes and found that interpolating cepstral
coefficients "does not shift the peaks of the spectral envelope in frequency", while
interpolating line spectral frequencies both shifts the formant peaks and moves spectral-shape
descriptors (centroid, spread, skewness, kurtosis) close to a straight line in the morph
parameter. Ezzat et al. (2005) reach the same end for speech with a one-dimensional optical flow
over the envelope, warping both envelopes toward each other before blending, so that formant
trajectories "follow linear paths". The evidence is not unanimous: Ezzat et al. cite work showing
that crossfaded line spectral frequencies do not shift formants properly either, since pole pairs
and formants are not one to one, and Slaney, Covell and Lassiter found in limited testing that a
warped smooth spectrogram sounded worse than a crossfaded one. What the envelope route's measured
timbre travel amounts to, then, is a decibel blend of two smooth shapes, which is a real change
of brightness and tilt and a dissolve of any resonance that stands at a different place in the
two sounds.

### In a learned model, position comes only from a named transformation

Across the pitch estimation and representation literature, a coordinate turned out to be
position-like in exactly one circumstance: the training data contained pairs `(x, T_k x)` for a
known transformation `T` and a known amount `k`, and the loss required the coordinate to move by
`k`.

- SPICE (Gfeller et al. 2020) regresses a scalar from two constant-Q crops offset by a known
  number of bins, with a loss on the difference of the two scalars against the offset; the scalar
  is linear in log-pitch, and a convex combination of two such scalars is itself a pitch. Raw
  pitch accuracy 90.6% on MIR-1K; without its reconstruction decoder the coordinate collapses to
  55.9%.
- PESTO (Riou et al. 2023) outputs a distribution over bins and asks that a shift of the input
  shift the output; with a shift-preserving Toeplitz head it reaches 96.1% on MIR-1K with 29
  thousand parameters, trained in hours on one older card; without the equivariance term or the
  Toeplitz head accuracy falls to about 6%, which is collapse. A distribution, though, crossfades
  under convex combination; the position has to be read out before interpolating.
- STONE (Kong et al. 2024) puts key on a circle: two crops of a constant-Q transform a known
  number of bins apart must give profiles whose cross-power spectral density has the phase of
  that shift. Key accuracy 77–79% against 81% supervised; without the phase term, 31%.
- Lattner, Dörfler and Arzt (2019) train a complex autoencoder on constant-Q pairs transposed or
  time-shifted by known amounts so that the magnitude of the code is invariant and the phase
  difference carries the transformation.
- Topographic VAEs (Keller and Welling 2021) encode an observed transformation as a cyclic roll
  within a capsule, with a correlation of 1.0 between the roll and the true factor shift; the
  commutative Lie group VAE (Zhu, Xu and Tao 2021) feeds the decoder a group element
  `exp(Σ tᵢAᵢ)`, so a straight line in `t` composes transformations by construction. Both were
  shown on synthetic image factors.

The generic self-supervised encoders do the opposite. Layer-wise probes of wav2vec 2.0 (Pasad,
Chou and Livescu 2021), MusicFM and MuQ (Zhou, Zhu and Chen 2025) and several speech models
(Sadok and Alameda-Pineda 2026) find pitch best read from the layers closest to the mel input,
where the representation correlates with the filterbank above 0.75; depth, compression and
linearization remove it. Invariance augmentations remove it actively: adding pitch-shift
invariance to a contrastive music encoder cost 10 points of pitch accuracy and 40 points of key
accuracy, and time-stretch invariance cost 34 points of tempo accuracy (Guinot, Quinton and
Fazekas 2024). A high classification score is no evidence of a position coordinate: Music2Latent
and the Stable Audio VAE reach 99.8% pitch-class F1 in a 64-dimensional reconstruction latent
(Pasini, Lattner and Fazekas 2024), which a which-bin-is-lit code gives as readily, and neither
paper mentions interpolation. No published measurement of straight-line interpolation in a neural
codec latent was found.

### One regularizer made an unnamed feature interpolable

ACAI (Berthelot et al. 2018) trains a critic to predict the interpolation weight from a decoded
interpolant, and trains the autoencoder to make every interpolant look like a reconstruction. On
a benchmark whose data manifold is one variable, the angle of a line, a plain autoencoder
superimposes two lines at the midpoint (mean distance to the true intermediate 6.88) while ACAI
moves the line (0.24), a factor of about thirty, with nothing naming the angle. Beckham et al.
(2019) obtain a weaker version with a real-versus-fake discriminator and with coordinate-wise
swaps between two codes. Chen et al. (2020) regularize the decoder's metric so that straight
latent paths are geodesics on the data manifold, which is only meaningful for a nonlinear
decoder, since an affine one is already flat and still crossfades. None of these has been applied
to audio.

### A timbre latent that interpolates: small, dense, and kept away from pitch

In the disentanglement literature the coordinate for pitch is nearly always categorical (a class,
a one-hot, a binarized code), which can switch and cannot travel, and timbre is a small Gaussian
latent that interpolates coherently at a fixed pitch. What kept pitch out of that latent, in
order of evidence: an adversarial pitch classifier on the feature (GANStrument, Narita, Shimizu
and Akama 2023: pitch readable from the timbre feature 17.4% → 2.6%, and the generated pitch
under latent interpolation 0.757 → 0.870), a capacity bottleneck on the pitch path (DisMix, Luo
et al. 2024: instrument accuracy 100% → 46.7% without it even with pitch labels), a KL prior on
the timbre path (pGESAM, Limberg et al. 2025, where removing it made interpolants "less smooth
and coherent"), and the envelope/fine-structure split with pitch-shift and effect augmentations
(Tanaka et al. 2022, trained on 62,704 pitched and 2,970 percussive sounds). Large "timbre"
embeddings leak pitch and tempo regardless (Ibáñez-Martínez et al. 2026: invariance to pitch
shift 0.49–0.67). The models that interpolate well keep the latent at 2 to 16 dimensions.

DDSP (Engel et al. 2020) is the cleanest demonstration of a position coordinate consumed by a
decoder: the fundamental frequency drives an oscillator, so interpolating it between two notes
gives a note within 0.07 semitones of the interpolated target. Its timbre latent is unregularized
and only empirically smooth, and the model is monophonic by construction. A decoder trained to
*move* partials from a spectrogram loss needs a horizontal term: with a bin-wise multi-scale
spectral loss, joint pitch estimation converged in one of five runs, while a one-dimensional
Wasserstein spectral loss gave a median raw pitch accuracy of 99.7% but "struggled" on real
instrument notes (Torres, Peeters and Richard 2024).

Descriptor regularization buys feature-linear interpolation at a small cost in fidelity. Le
Vaillant and Dutoit (2024) force latent dimensions to vary monotonically with timbre descriptors
and measure the linearity and smoothness of descriptor trajectories over nine morph steps; the
regularization improved linearity, and in a listening test with 25 participants smoothness and
naturalness ratings were the same judgment, with 88% of the variance shared.

### How morphs are judged

The field's shared definition (Caetano and Osaka 2012, read second-hand) has three parts:
correspondence, in that the elements of the description are intermediate; intermediateness, in
that listeners hear the result as between the two; and smoothness, in that equal steps of the
parameter give equal perceptual steps. The cheapest protocol that separates a move from a
dissolve is Caetano's ladder: the source, nine intermediates and the target played as one
sequence, and a forced choice between two ladders on smoothness. Two cautions from recent
listening tests: untrained listeners called a plain mix a morph 64% of the time (Chu et al.
2026), and embedding-based intermediateness scores reward "both present", which a mix satisfies.
On temporal structure, listeners rated a true midpoint of event count and spacing at 4.30
against 3.40 for one sound's timing under the other's spectrum and 2.75 for a mix (Dixit et al.
2025), which is a mark against the envelope route's rule that rhythm belongs to the kept
excitation.

For a learned latent the tests that matter are continuous: regress the known shift from the
coordinate, check equivariance and invariance under pitch shift and time stretch (the protocol of
Ibáñez-Martínez et al. 2026), and read the midpoint of a pair for one moving peak rather than two,
which is what the note-count reading built for the partials route already does.

## What this says about the routes we have

| Finding | The literature's name for it | The published remedy |
|---|---|---|
| The transport warbles on chords | per-frame transport plans are not temporally consistent (Henderson and Solomon 2019) | one correspondence per pair, applied over time (Roma et al. 2020; Valdivia et al. 2025) |
| Matched partials leave two pitch contents in the middle | two pitches make two auditory objects (Slaney et al. 1996); "no obvious correspondence" for polyphony (Fitz et al. 2002) | pair at the level of notes with minimal total movement and no crossing (Tymoczko 2006), with a phantom partner for every orphan; nobody has run this on audio |
| The envelope route's pitch content can only switch | the excitation crossfades at fixed coordinates | warp the excitation's frequency axis along a pitch path before crossfading (Slaney et al. 1996), which turns the switch into a glide for one pitch |
| The envelope route's timbre travel is bounded | cepstral interpolation does not shift resonance peaks (Caetano and Rodet 2013) | line spectral frequencies or an envelope flow as the resonance coordinate |
| The middle of two chords is dissonant | paths between chords leave the equal-tempered lattice and pass near clustered, dissonant regions (Tymoczko 2006) | choose the voice leading; the dissonance itself is not removable |

## Two ways to condition an embedding

The question at the top has two answers in the literature, with different kinds of evidence.

**Name the transformations.** Build training pairs from transformations whose amount is known
(a pitch shift of `k` bins along the log-frequency axis, a time stretch by a factor, a scaling of
the decay, a tilt of the spectrum) and ask a coordinate to move by that amount. This is the only
recipe with audio precedents, and every precedent worked: SPICE, PESTO, STONE, Lattner's complex
autoencoder. Its limit is that it makes coordinates only for the transformations one names, and a
morph between two unrelated sounds also has to move what nobody named.

**Let a critic find them.** Decode interpolants and train a critic to tell them from real
sounds, so the autoencoder has to organize its coordinates such that convex combinations decode
to sounds a critic cannot place between the ends. This is the only mechanism shown to turn an
unnamed feature into a movable coordinate, and it did so by a factor of thirty on a one-factor
benchmark. It has no audio precedent, and its critic is easily satisfied by a decoder that
switches at the midpoint rather than glides, so it needs the ladder test and not only the
midpoint test.

Both share prerequisites this repository already meets: an input axis on which a pitch shift is a
translation (the log-frequency geometry), free transformation pairs (a tracker sample played at
two rates is the same sound transposed, and the training cache holds retuned views), a
nonlinear decoder, and an instrument that reads a midpoint for one pitch content or two.

## The plan

Cheapest decisive question first; every step leaves something usable even if the next one fails.

**Step 0. Two classical upgrades to the envelope route, no training.** First, where both sounds
hold one pitch, warp the kept excitation's frequency axis along the pitch path between the two
fundamentals before the envelope is applied, so the pitch glides and the switch remains only for
chords. Second, render the envelope path in line spectral frequencies from an all-pole fit beside
the cepstral path, and read both with the spectral-shape linearity that Caetano and Rodet used.
Both are a few days' work on the shipped route and are heard on the existing listening pairs.

**Step 1. The critic on the existing autoencoder.** Add an ACAI critic to the grid codec's
training and measure the one thing it should change: for a sample heard at two rates, whose true
midpoint is the same sample at the rate between them, does the decoded midpoint read as one pitch
at the geometric mean, or as two? The transposition reading in the comparison tables already
measures exactly this. Success here is the user's hypothesis confirmed on real material: features
found without being named. Failure is informative too, since it says the critic needs the
coordinates of step 2 to work with.

**Step 2. Named coordinates on the log-frequency analysis.** A transposition-equivariant pitch
head in the PESTO style, trained on rolled analyses of the library's own sounds, giving a scalar
log-pitch coordinate and a reliability that says whether a coherent series is there at all, which
is what separates a drum from a bass. The same recipe with time stretch gives a duration and decay
coordinate, and with a spectral tilt a brightness coordinate. Each is tested by regressing the
known shift, not by classifying it. These nets are tens of thousands of parameters and train in
hours.

**Step 3. The decodable model.** An encoder that reads the coordinates of step 2 beside a small
timbre latent of 8 to 16 dimensions, kept free of pitch and duration by the same sample at two
rates mapping to one latent, an adversarial pitch classifier, and a KL prior; a decoder that
consumes the coordinates as positions, either a synthesizer (the oscillator bank at the pitch
coordinate, an all-pole filter in line spectral frequencies, a noise level) or a spectrogram
decoder under the critic of step 1, made audible by phase gradient heap integration; a
reconstruction loss plus the critic. A morph interpolates the coordinates and the latent and
decodes. The embedding for the cloud is the coordinates beside the latent: axes a person can name
(pitch, duration, decay, brightness) and a residual that says which instrument. The probes of
Ibáñez-Martínez et al. (2026) say whether it holds.

**Judging every step.** The midpoint note-count reading for one pitch content; the linearity and
smoothness of descriptor trajectories over nine steps; the equivariance and invariance probes;
and the ladder listening test with the standing threshold (two bad examples dismiss a method,
four good ones promise it). Classification accuracy of any kind is not evidence.

## What stays open

Chords. No verified method morphs two chords with different pitch sets while keeping one object,
and the dissonance in the middle is not a defect to fix but a property of the space: every path
between two consonances crosses less consonant ground. The coordinates of steps 2 and 3 are
scalars, one pitch per sound; a chord needs a set of them, which is the object-level
factorization DisMix (Luo et al. 2024) and the self-supervised multi-pitch salience of Cwitkowitz
and Duan (2024) begin to give, and Tymoczko's voice leading says how such a set should travel.
That is a later plan. Until then a chord's pitch content changes hands at one point of the path,
as the envelope route does now.

## Sources

Read in full text unless marked. Numbers in the text are quoted from these.

Classical and transport morphing:
Slaney, Covell, Lassiter, "Automatic audio morphing", ICASSP 1996 —
https://engineering.purdue.edu/~malcolm/interval/1995-061/ ·
Tellman, Haken, Holloway, "Timbre morphing of sounds with unequal numbers of features", JAES 1995
(read through the group's ICMC 1994 poster, https://www.cerlsoundgroup.org/Homey/ICMC94Poster.html) ·
Fitz, Haken, Lefvert, O'Donnell, "Sound morphing using Loris", ICMC 2002 —
https://www.cerlsoundgroup.org/Loris/papers/icmc2002.pre.pdf ·
Osaka, "Timbre interpolation of sounds using a sinusoidal model", ICMC 1995 (second-hand) ·
Henderson, Solomon, "Audio transport: a generalized portamento via optimal transport", DAFx 2019 —
https://arxiv.org/abs/1906.06763 ·
Valdivia, Renaud, Cazelles, Févotte, "Audio signal interpolation using optimal transportation of
spectrograms", arXiv 2025 — https://arxiv.org/abs/2502.15430 ·
Roma, Green, Tremblay, "Audio morphing using matrix decomposition and optimal transport", DAFx 2020 —
https://dafx2020.mdw.ac.at/proceedings/papers/DAFx2020_paper_42.pdf ·
Ezzat, Meyers, Glass, Poggio, "Morphing spectral envelopes using audio flow", Interspeech 2005 —
http://people.csail.mit.edu/tonebone/publications/audioflow.pdf ·
Paliwal, "Interpolation properties of linear prediction parametric representations", Eurospeech
1995 (scan; numbers taken from Islam, "Interpolation of linear prediction coefficients for speech
coding", McGill 2000, https://www.collectionscanada.gc.ca/obj/s4/f2/dsk1/tape4/PQDD_0034/MQ64229.pdf) ·
Caetano, Rodet, "Musical instrument sound morphing guided by perceptually motivated features",
IEEE TASLP 2013 — http://articles.ircam.fr/textes/Caetano13a/index.pdf ·
Caetano, Osaka, "A formal evaluation framework for sound morphing", ICMC 2012 (second-hand;
protocol read at http://recherche.ircam.fr/anasyn/caetano/survey/smoothness.html) ·
Kazazis, Depalle, McAdams, "Sound morphing by audio descriptors and parameter interpolation",
DAFx 2016 — https://www.dafx.de/paper-archive/2016/dafxpapers/21-DAFx-16_paper_46-PN.pdf ·
Tymoczko, "The geometry of musical chords", Science 2006 —
https://dmitri.mycpanel.princeton.edu/files/publications/science.pdf.

Position from named transformations:
Gfeller et al., "SPICE: Self-supervised pitch estimation", TASLP 2020 — https://arxiv.org/abs/1910.11664 ·
Riou, Lattner, Hadjeres, Peeters, "PESTO", ISMIR 2023 — https://arxiv.org/abs/2309.02265 ·
Kong et al., "STONE: Self-supervised tonality estimator", ISMIR 2024 — https://arxiv.org/abs/2407.07408 ·
Lattner, Dörfler, Arzt, "Learning complex basis functions for invariant representations of
audio", ISMIR 2019 — https://arxiv.org/abs/1907.05982 ·
Marincione et al., "PHALAR: Phasors for learned musical audio representations", ICML 2026 —
https://arxiv.org/abs/2605.03929 ·
Keller, Welling, "Topographic VAEs learn equivariant capsules", NeurIPS 2021 — https://arxiv.org/abs/2109.01394 ·
Zhu, Xu, Tao, "Commutative Lie group VAE for disentanglement learning", ICML 2021 — https://arxiv.org/abs/2106.03375 ·
Löwe et al., "Complex-valued autoencoders for object discovery", TMLR 2022 — https://arxiv.org/abs/2204.02075 ·
Cwitkowitz, Duan, "Toward fully self-supervised multi-pitch estimation", arXiv 2024 — https://arxiv.org/abs/2402.15569 ·
Torres, Peeters, Richard, "Unsupervised harmonic parameter estimation using differentiable DSP
and spectral optimal transport", ICASSP 2024 — https://arxiv.org/abs/2312.14507.

What generic self-supervision encodes:
Pasad, Chou, Livescu, "Layer-wise analysis of a self-supervised speech representation model",
ASRU 2021 — https://arxiv.org/abs/2107.04734 ·
Zhou, Zhu, Chen, "Layer-wise investigation of large-scale self-supervised music representation
models", arXiv 2025 — https://arxiv.org/abs/2505.16306 ·
Sadok, Alameda-Pineda, "InsideSSL", arXiv 2026 — https://arxiv.org/abs/2607.06392 ·
Guinot, Quinton, Fazekas, "Leave-one-equivariant", arXiv 2024 — https://arxiv.org/abs/2412.18955 ·
Pasini, Lattner, Fazekas, "Music2Latent", ISMIR 2024 — https://arxiv.org/abs/2408.06500.

Interpolation regularizers:
Berthelot, Raffel, Roy, Goodfellow, "Understanding and improving interpolation in autoencoders
via an adversarial regularizer", ICLR 2019 — https://arxiv.org/abs/1807.07543 ·
Beckham et al., "On adversarial mixup resynthesis", NeurIPS 2019 — https://arxiv.org/abs/1903.02709 ·
Chen et al., "Learning flat latent manifolds with VAEs", ICML 2020 — https://arxiv.org/abs/2002.04881.

Pitch–timbre disentanglement and timbre spaces:
Luo, Agres, Herremans, ISMIR 2019 — https://arxiv.org/abs/1906.08152 ·
Luo et al., ISMIR 2020 — https://archives.ismir.net/ismir2020/paper/000162.pdf ·
Tanaka et al., APSIPA 2022 — http://www.apsipa.org/proceedings/2022/APSIPA%202022/WedAM1-7/1570840401.pdf ·
Luo et al., "DisMix", arXiv 2024 — https://arxiv.org/abs/2408.10807 ·
Engel et al., "DDSP", ICLR 2020 — https://arxiv.org/abs/2001.04643 ·
Engel et al., "GANSynth", ICLR 2019 — https://arxiv.org/abs/1902.08710 ·
Engel et al., "NSynth", ICML 2017 — https://arxiv.org/abs/1704.01279 ·
Narita, Shimizu, Akama, "GANStrument", ICASSP 2023 — https://arxiv.org/abs/2211.05385 ·
Limberg et al., "pGESAM", DAFx 2025 — https://arxiv.org/abs/2510.04339 ·
Esling, Chemla-Romeu-Santos, Bitton, "Generative timbre spaces", DAFx 2018 — https://arxiv.org/abs/1805.08501 ·
Le Vaillant, Dutoit, "Latent space interpolation of synthesizer parameters using
timbre-regularized auto-encoders", TASLP 2024 — https://arxiv.org/abs/2210.16984 ·
Ibáñez-Martínez et al., "Evaluating disentangled representations for controllable music
generation", arXiv 2026 — https://arxiv.org/abs/2602.10058 ·
Wilkins et al., "Balancing information preservation and disentanglement", 2025 — https://arxiv.org/abs/2507.22995 ·
Bitton, Esling, Harada, "Neural granular sound synthesis", 2020 — https://arxiv.org/abs/2008.01393.

Evaluation and recent neural morphing:
Niu, Zhang, Martin, "SoundMorpher", arXiv 2024 — https://arxiv.org/abs/2410.02144 ·
Kamath, Gupta, Nanayakkara, "MorphFader", arXiv 2024 — https://arxiv.org/abs/2408.07260 ·
Chu et al., "Mix2Morph", ICASSP 2026 — https://arxiv.org/abs/2601.20426 ·
Dixit, Park, Donahue, Heller, "Learning perceptually relevant temporal envelope morphing",
WASPAA 2025 — https://arxiv.org/abs/2506.01588.
