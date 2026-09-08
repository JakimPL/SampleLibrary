# Considered, rejected, deferred

This document exists so the same ground is not walked twice. Several of the entries below were
reached by measurement or by the user's direct judgment, and the reasons matter more than the
verdicts — a rejection whose reason stops applying should be revisited, and an entry marked deferred
is waiting for something specific.

## Rejected

### Extending the invariant backend into a decoder

**Reason: impossible by construction, not merely hard.** CQHC achieves pitch invariance by taking
the magnitude of the Fourier transform along the log-frequency axis, which discards the shift — and
the shift is the pitch. The envelope half is peak-normalized and resampled to 32 duration-fraction
points, discarding gain and absolute duration. The information a decoder would need is gone before
the descriptor is assembled.

**Keep the backend.** It wins transposition retrieval decisively and it is cheap. Under the new
scheme it becomes the reference a learned latent has to beat.

### Picking one true rate per sample

**Reason: it manufactures a fact the corpus does not have.** 6,972 hashes (5.5%) are used at more
than one declared rate, spread by an octave at the median and up to six octaves. Choosing the modal
rate is wrong by an octave for those, and arbitrary for a sample used at twelve rates.

Already rejected once by the user when it was proposed as the fix for the rate-mislabeling finding.

### Detecting the pitch and normalizing to it

**Reason: it fails silently on percussion.** Pitch detection needs a fundamental. Six of the
fourteen categories are percussive, the corpus is full of drums, noise and single-cycle fragments,
and a method that works on tonal material while producing nonsense elsewhere is worse than none.

Also already rejected by the user. What replaced both framings is in
[`02-representation.md`](02-representation.md): the stored waveform is the reference frame and every
nuisance transform is relative to it.

### Morphing by inverting the 2D projection

**Reason: the user placed morphing outside the projection, and the inverse is very lossy.** Mapping
two dimensions back to a latent of any useful size throws away almost everything, so the sound would
be governed mostly by the inverse's own guesswork rather than by the gesture.

`umap.UMAP.inverse_transform` does exist and works on a Euclidean fit, so this remains available for
other purposes — placing a point, exploring a region. It is not the control surface for a morph.
Note that `reduce_and_persist_coordinates` refits from scratch every run and never persists the
fitted model, so using the inverse at all would mean persisting one.

### A direct phase-vocoder blend of two signals

**Reason: tried on this project and rejected.** A notebook doing exactly this was built in an
earlier session and deleted at the user's request, including from git history — its commits no
longer exist, so there is nothing to resurrect. The objection was not to the implementation but to
the concept: blending two waveforms dissolves one into the other, which is not a sound *between*
them.

**This is the most likely way to accidentally rebuild a rejected result.** A naive spectral
crossfade inside the new package produces the same thing wearing a better name. The morph
plausibility metric in [`05-evaluation.md`](05-evaluation.md) exists to catch it.

### A plain autoencoder, with no probabilistic or quantized bottleneck

**Reason: it is trained only on points that correspond to real samples, so it has no reason to
behave anywhere between them.** Reconstruction may look excellent while every intermediate point
decodes to noise, and the failure is invisible in every metric except the ones that actually
interpolate. A KL term or a vector-quantized codebook with a prior is what makes an intermediate
point mean something, and it is the single easiest thing to leave out.

### Contrastive-only embeddings

**Reason: undecodable, so goal 3 is out of reach.** A contrastive objective over free positives —
resampled variants, equivalence classes, shared names — would likely beat everything here on
retrieval. It produces no decoder. Contrastive terms are worth keeping *as auxiliary supervision on
a latent that also reconstructs*, which is what [`02-representation.md`](02-representation.md)
proposes; as the whole objective they answer the wrong question.

### DDSP harmonic-plus-noise as the primary decoder

**Reason: the corpus is the wrong shape for it, twice over.** It models a harmonic series plus
filtered noise, which is excellent for sustained tonal material and weak for the percussion this
library is largely made of. And it needs an f0 track, which runs straight back into the pitch
detection rejected above.

It gives genuinely musical control, so it may return for a tonal subset once the note-event signal
can identify one.

### Diffusion as a starting point

**Reason: too slow to iterate on for the insight-gathering the user asked to do first.** A diffusion
vocoder or generator would likely produce the best audio here, and it costs days per experiment and
seconds per sample at inference. The instruction was to start with what can be implemented and
tested quickly. It is a Stage 4 or later option.

### The dev-library sandbox for listening tests

**Reason: its samples are 40–100 ms synthetic tones built to exercise equivalence detection.** They
are fine for checking that a pipeline runs and useless for judging whether something sounds like
music. A morph demo was built against them once and the result was rightly called useless. Every
listening test uses real samples from the real library.

### A new table for latents

**Reason: `sample_feature_vector` scoped by `Experiment` already is one.** It is an `ARRAY(Double)`
keyed on `(experiment_id, sample_hash)`, two experiments hold independent vectors for the same
sample without collision, and a codec adapted to `FeatureExtractor` reaches the sample cloud through
the existing pipeline with no change to it. `Experiment.params` is already plumbed and unused, ready
to record a codec's configuration.

### Copying the catalog to the GPU machine

**Reason: the user chose to rebuild.** Transferring `objects/` (3.9 GB) plus a `pg_dump` (3.2 GB,
of which 2.8 GB is note events) was the alternative. Rebuilding from the module collection already
present costs a couple of hours and gives the sharded parallel extraction its first test on a second
machine, which the project wants anyway.

## Deferred

### RAVE and waveform-domain codecs

**Explicitly not off the table.** Waiting for the cheap stages to produce metrics and a working
definition of "good" for this corpus. Stage 5 in [`04-roadmap.md`](04-roadmap.md). On 12 GB it needs
a reduced batch size and gradient accumulation. The `SampleCodec` protocol was shaped so that a
waveform-domain model implements it directly, with no canonicalizer and no vocoder.

### `make equivalence` at full scale

**Blocked on a redesign, and worth knowing before it is attempted.** `detect_equivalences` reads
every sample's WAV and keeps the trimmed float64 array in a dictionary that is never evicted, so a
full pass holds the decoded corpus in RAM — about 23 GB at float64, against 3.9 GB on disk. Its
gain-variant candidate generation sorts by frame count and sweeps neighbors, which degenerates
toward quadratic on tens of thousands of short samples clustered in the same length band. Budget
hours and over 20 GB of RAM at 127k.

**What stays unavailable until it runs:** `sample_relation` is empty, so every sample is its own
equivalence class. Group annotation reaches exactly one sample and the "apply to all N
near-duplicates" control never appears. The near-duplicate retrieval evaluation has no ground truth,
and the category kNN split falls back to a plain stratified one. The other four metrics are
unaffected.

A streaming redesign — fingerprint in one pass without retaining waveforms, and a blocked candidate
sweep — is the unblocking work.

### The `+absolute` descriptor variant

Measured +2.1 points on transposition retrieval and +1.2 on category agreement, against −3.8 on
bass. A judgment call that was left unmade rather than decided. It is a small, self-contained
experiment for whoever has the harness running.

### Multiscale envelope localization for transients

The user's own idea for the invariant descriptor, never tested.

### The unexplained cymbal, pad and vocal deficit

The invariant backend loses to librosa specifically on those three categories. Three explanations
were proposed and all three refuted by measurement. The remaining untested hypothesis: librosa's 13
MFCCs with mean, standard deviation *and* frame-to-frame deltas describe spectral-envelope shape and
its articulation more finely than 20 CQHC coefficients at 8 time points. The per-category breakdown
in the new harness is the place to pick this up.

### A real per-module embedding

`samplecloud.placeholder_modules` seeds a module's coordinates from its own hash, and
`GET /cloud/modules` is documented as temporary. A genuine module embedding built on whatever
per-sample metric wins is the pending work.

### The eight modules that genuinely lost their samples

Of 120 modules holding zero sample occurrences, 112 are chiptunes correctly excluded by the
512-frame floor and 8 are a real gap — most likely stale rows from an ingest predating a `trackmod`
reader improvement. Re-ingesting those 8 would close it.

### Postgres role hardening for the curation write path

The write path is narrow by construction rather than by permission. Real enforcement needs a second
role. Deferred by the user.

### Morphing between more than two points

The user's instruction is explicit: two points and a weight first, and extend only if that succeeds.

### Loop-aware morphing

36% of occurrences loop, so their stored length understates how long the sound is heard.
Canonicalization describes the stored waveform and treats loop points as metadata beside it. Whether
a morph should carry loop structure is open until there is a morph worth looping.

### An index structure for similarity search

`GET /samples/{hash}/similar` loads the whole `sample_spectral_feature` table per request and scans
it. Fine at the 25,000 rows currently stored; at 127,492 it needs an index.

## Open questions

- **Is Griffin-Lim good enough?** Objectively its magnitude round trip loses little — 4.72 dB median
  log-mel RMSE against 22.70 dB between unrelated samples. That measure is blind to phase, which is
  exactly where Griffin-Lim fails. Stage 2 settles it by listening, and the answer decides whether
  Stage 4 exists at all.
- **Does a learned latent beat PCA at this corpus size?** 127k samples is a real dataset and a small
  one. PCA is exactly invertible and free. Stage 3 has to earn its place on both reconstruction and
  retrieval.
- **Mel or constant-Q?** Constant-Q gives exact translation equivariance including in the bass,
  where the largest keyword category lives; mel inverts more cleanly and costs a quarter as much.
  Both are implemented and measured rather than argued about.
- **Stream a morph, or cache it content-addressed?** Streaming is simpler and costs a synthesis per
  request. Caching gives the result an identity the existing player already understands, at the cost
  of the first server-side write into the audio store.
- **MLflow, or a lighter run log?** The user raised MLflow. The requirement is only that runs stay
  out of the repository.
