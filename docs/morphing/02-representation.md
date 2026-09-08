# What the representation has to be

This is the reasoning the rest of the work rests on. It is worth reading before the architecture,
because several decisions there look arbitrary until this argument is in hand.

## The three goals ask for two different objects

The library wants embeddings that

1. reasonably reflect perceptual differences between samples,
2. classify samples once hand labels exist, and
3. allow generating a sample from an intermediate point between two others.

Goals 1 and 2 want a **descriptor**: any fixed-length vector that separates things well. Nothing has
to be recoverable from it. Goal 3 wants a **code**: a representation with a decoder, from which
audio can be produced. That is a strictly stronger object, and the difference is not a matter of
degree.

The hope is that one representation serves all three. It can — under a condition set out at the end
of this document — but only if the design starts from the harder requirement.

## The current backend is undecodable by construction

`InvariantFeatureExtractor` is good at what it does, and there is no path from it to goal 3.

Its spectral half computes a Constant-Q Harmonic Coefficient descriptor: it takes the CQT magnitude,
Fourier-transforms along the log-frequency axis, and keeps **the magnitude** of that transform. A
rate or pitch change is a multiplicative scaling in linear frequency, which is an additive shift
along a log-frequency axis, and taking the magnitude of the shifted axis's own transform discards
the shift exactly. That is the whole trick, and it is why the backend wins transposition retrieval
95.5% against 8.2%.

But the shift *is* the pitch. Discarding it discards the information needed to reconstruct the
sound. Its envelope half is peak-normalized and resampled to 32 duration-fraction points, discarding
gain and absolute duration for the same kind of reason.

So the properties that make this descriptor excellent for goal 1 are precisely the properties that
make it useless for goal 3. It should be kept — under the scheme below it becomes the reference any
learned representation has to beat on retrieval — and it should not be extended.

**The general lesson, which shapes everything below:** invariance obtained by *destroying* a
variable cannot be inverted. Invariance obtained by *factoring the variable out* can.

## There is no true rate

The obvious move is to resample everything to a common rate before analysis, so that transposition
stops confusing the model. It fails here, and it has already been rejected twice on this project.

The stored WAV header always says 44,100 Hz, and that number is fiction — a container convention,
not a measurement. The real reference rate lives per *occurrence*, in `sample_properties.rate`, as
the rate the waveform is read at when tracker C-5 is pressed.

One content hash can carry several of them. Measured over the catalog: **6,972 hashes (5.5%) are
used at more than one declared rate**, and where they are, the spread is a full octave at the median
and seventeen semitones at p90, reaching six octaves at the extreme. A tracker instrument reads one
waveform at whatever rate a slot asks for; that is how the format works.

Two framings were considered and rejected before this document:

- **Pick a rate per sample** — the modal rate, say. It manufactures a fact the corpus does not have.
  For the 5.5% it is wrong by an octave, and for a sample used at twelve rates it is arbitrary.
- **Detect the pitch and normalize to it.** Pitch detection needs a fundamental. Six of the
  fourteen sample categories are percussive, and the corpus is full of drums, noise and single-cycle
  fragments that have no fundamental to find. A method that works for tonal material and silently
  produces nonsense for percussion is worse than no method.

**The resolution: the stored waveform is the reference frame.** Every nuisance transform is expressed
*relative to it*, and no absolute rate is ever asserted. This costs nothing, because everything
below only ever needs relative quantities.

## The nuisance group is time-scaling and gain

For a tracker one-shot, two transforms carry no information about what the sound *is*:

- **Time-scaling.** Reading the same waveform at a different rate scales it in time, which changes
  pitch and duration together. In tracker terms there is no separate pitch control; the rate is the
  pitch. Trimming and looping also change duration, independently of pitch.
- **Gain.** A sample is stored at whatever level it was ripped at, and level is a mixing decision.
  This is more consequential than it sounds: measured on the existing descriptor, an unclipped 0.5×
  gain change moved the standardized vector 9.32 and a 0.25× change moved it 14.02, both past the
  corpus's own median distance between unrelated samples.

Everything else — the spectral envelope, its motion over time, the attack, the noise character — is
what the representation should carry.

## On a log-frequency axis, a rate change is a translation

This is the observation the design turns on.

Resampling by a factor α maps a signal `x(t)` to `x(αt)`. In the frequency domain that scales the
frequency axis by α. On a **logarithmic** frequency axis, a multiplicative scaling becomes an
**additive shift**: `log(f/α) = log f − log α`. Meanwhile the duration scales by `1/α`, so if the
time axis is expressed as a **fraction of the clip's own duration** rather than in seconds, the time
axis is left unchanged.

Put those together and a canonical image on a (log-frequency × duration-fraction) grid has this
property: **two recordings of the same waveform at different rates produce the same image, translated
vertically.** Nothing else changes. The relation is exact in the continuous idealization and
approximate at the resolution limits of a real transform, which is good enough to build on — it is
the same relation CQHC already exploits.

That gives two ways to be rate-invariant:

- Destroy the translation, as CQHC does. Invariant, undecodable.
- **Condition on the translation.** The image is translation-equivariant, so a model can be told how
  far the content sits from the reference and learn everything else. Invariant in the latent,
  and fully invertible.

The second is the whole design.

## Mel or constant-Q is an experiment, not a decision

The pure-translation property needs a genuinely logarithmic frequency axis.

- **Constant-Q** is exactly logarithmic by construction, so the property holds across the whole
  range. Its inverse (`librosa.icqt`, `librosa.griffinlim_cqt`) is more approximate, and it costs
  about four times a mel spectrogram — measured here at ~79 minutes single-core over the catalog
  against ~21.5 minutes.
- **Mel** is approximately linear below roughly 1 kHz and logarithmic above it. So the translation
  property degrades exactly where bass content lives — and bass is the largest keyword category in
  this corpus, and the one an earlier descriptor variant regressed on by 3.8 points. Mel inverts
  more cleanly and is cheaper.

Neither dominates, so the canonicalizer is one of the swappable axes in
[`03-architecture.md`](03-architecture.md) and the choice is settled by measurement rather than by
argument.

## The conditioners

Each sample is canonicalized into a fixed-size image plus three scalars, all expressed relative to
the stored waveform:

| Conditioner | Meaning |
|---|---|
| Frequency translation, in semitones | how far the content is shifted from the reference frame |
| Log canonical duration | how long the sound is, having normalized the time axis away |
| Log gain | the level, having peak-normalized the image |

Translation and duration move together under resampling and move independently under trimming, so
both are carried. Absolute rate never appears.

The corpus states its own realistic range for the translation: an octave at the median, seventeen
semitones at p90. That is the range to draw training augmentations and transposition-retrieval
trials from, rather than an arbitrary ±24.

**One open matter to keep in view:** 36% of occurrences loop, so their stored length understates how
long the sound is heard. Canonicalization describes the stored waveform, and loop points are
metadata beside it. Whether a morph should carry loop structure is left open until there is a morph
worth looping.

## Morphing

Morphing is a convex combination of two samples at a weight `t` in `[0, 1]`:

```
morph(a, b, t) = decode( lerp(z_a, z_b, t),  lerp(c_a, c_b, t) )
```

with the latent `z` and the conditioners `c` interpolated separately, so the two can be controlled
independently — timbre morphed at constant pitch, or pitch glided at constant timbre. That
separation is most of what makes the result musical rather than a wash.

Morphing does not live in the 2D projection. Two dimensions cannot carry a latent of any useful
size, and inverting the projection would put a very lossy step between the user's gesture and the
sound. The cloud stays a way to *find* samples; the morph runs between two chosen ones. More than
two points is a later question, once two points work.

**This is a different object from a direct blend of two signals.** A phase-vocoder crossfade between
two waveforms was built on this project before and rejected: it dissolves one sound into the other
rather than producing a sound between them. A naive spectral crossfade in the new package would
reproduce that result exactly, and the metric in [`05-evaluation.md`](05-evaluation.md) that
distinguishes the two exists for this reason.

## Making one representation serve all three goals

A latent trained for reconstruction alone is a mediocre descriptor. Reconstruction spends capacity
on detail that carries no perceptual weight — the exact realization of a noise tail, 8-bit
quantization noise — while under-weighting salient but low-energy detail. That is the honest tension
in wanting one space.

Three terms resolve it, and all three are needed:

1. **A perceptual reconstruction loss**, multi-resolution spectral rather than plain squared error on
   a single representation, so the model is scored on something closer to what is heard.
2. **A bottleneck that makes intermediate points decodable** — a KL term, or a vector-quantized
   codebook with a prior. This is the single most important choice for goal 3, and it is easy to
   miss: a plain autoencoder is trained only on points that correspond to real samples, so it has no
   reason at all to produce anything sensible halfway between two of them. Without this term the
   morph is a lottery.
3. **Auxiliary supervision on the latent**, which is what pulls the space toward goals 1 and 2:
   contrastive positives generated for free by resampling a sample within the corpus's own
   transposition range, the 13,359 keyword categories, the note-event weak labels below, and hand
   labels as they arrive.

With all three, `z` is one space: UMAP over it is the cloud, distance in it is similarity, a small
head on it is the classifier, and the decoder makes it a morphing instrument.

## What goal 2 can be measured against today

There are **zero hand annotations**. Waiting for them would stall every judgment about the
representation. Two substitutes exist right now, and both are free:

- **The keyword categories** cover 13,359 samples, 10.5% of the catalog. Small and biased — those
  are the samples that came from well-named, well-organized modules — but they are real labels, and
  large enough for a held-out kNN evaluation with per-category breakdown.
- **Note events** say how each sample was actually played. In a 300-module probe, 41% of the
  samples a composer touched were struck at exactly one pitch, while the melodic remainder spanned a
  median of 15 distinct pitches over 27 semitones. That separates percussive from tonal material
  structurally, over far more of the catalog than names do, with nobody listening to anything.

Hand labels remain the eventual target, and they are the one artifact here no pipeline can rebuild.
When they arrive they join the auxiliary supervision above and become the primary evaluation set.
Until then, the work is measurable without them.
