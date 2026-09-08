# Roadmap

Cheapest first, on the user's own instruction: start with solutions that can be implemented and
tested quickly to gather data and insight, then substitute more advanced ones once there is
something to judge them against.

**Stop after each stage**, report what it did, and propose the next in a sentence. Every stage below
names what it delivers, what it has to beat, and the gate that decides whether the next one is worth
starting.

---

## Stage 0 — Rebuild the library

**Delivers:** a catalog and content store on this machine, and a measurement the project wants
independently: whether sharded parallel extraction works on a second machine.

Follow [`07-environment.md`](07-environment.md). Run four concurrent shards, then report wall clock
per shard and overall, and each run's ingested / already-known / ingested-by-another-run / failed
counts. Compare the resulting row counts against the shape in [`01-corpus.md`](01-corpus.md) — they
will differ a little, and a large divergence is worth understanding before building on it.

Thumbnails when you want the web UI. Notes only when Stage 1's weak-label metric is wanted.
Equivalence stays off; see [`06-alternatives.md`](06-alternatives.md).

**Gate:** `make check` green on a fresh clone, and a catalog roughly the expected size.

---

## Stage 1 — The evaluation harness

**Delivers:** committed, tested metric code, and honest baseline numbers for the two descriptors
that already exist.

Everything in [`05-evaluation.md`](05-evaluation.md). Nothing here needs a GPU.

This comes before any modeling for a specific reason: the standing figures for the existing backends
came from scripts that were never committed, so they cannot be reproduced, and one of them was
computed over a tenth of the catalog. Re-measure `invariant` and `librosa` over the full corpus and
publish the numbers. Every later claim is relative to these.

**Must beat:** nothing. It establishes the floor.

**Gate:** the numbers exist, the harness has tests, and re-running it reproduces them.

---

## Stage 2 — Canonicalizer, linear codec, Griffin-Lim

**Delivers:** the first audio. And the answer to the Griffin-Lim question.

No new dependencies: librosa already ships every inversion primitive needed, and scikit-learn ships
PCA and NMF. Build the `Canonicalizer`, `SampleCodec`, `Vocoder` and `Morpher` protocols and their
registries, a mel canonicalizer and a constant-Q one, a PCA codec, a Griffin-Lim vocoder, and a
latent-interpolation morpher. Add a CLI that renders audio to files.

**The experiment that matters.** Render, over a set of real samples chosen to span the categories:

- the reconstruction at `t = 0` and at `t = 1`,
- morphs at `t = 0.25`, `0.5`, `0.75`,
- and, as a control, the original audio.

Then listen. The reconstructions are the diagnostic: **if a reconstruction of a known sample sounds
wrong, the vocoder is at fault, not the codec** — the codec is PCA, which is exactly invertible, so
anything lost between original and reconstruction was lost in analysis and synthesis. That
separates the two questions cleanly and is why this stage uses a linear codec rather than a learned
one.

Use real samples from the real library. The dev-library sandbox's fixtures are 40–100 ms synthetic
tones built to exercise equivalence detection; a morph demo against them was built once before and
the result was rightly called useless.

**Must beat:** the log-mel reconstruction scale in [`01-corpus.md`](01-corpus.md) — Griffin-Lim
alone lands at 4.72 dB median against 22.70 dB between unrelated samples, so codec plus vocoder
should stay far below that 22.70 dB ceiling. On retrieval, PCA latents should be measured against
`invariant` and `librosa` even though they are unlikely to win; the number sets the price of
decodability.

**Gate:** the user has listened, and has an opinion about whether Griffin-Lim is good enough. That
opinion decides whether Stage 4 exists.

---

## Stage 3 — Conditional VAE codec

**Delivers:** a learned latent, and the answer to whether learning buys anything here.

Same canonicalizer, same vocoder, swapped codec — that is the point of the axes. Conditional on the
three conditioners from [`02-representation.md`](02-representation.md), with the three loss terms:
multi-resolution spectral reconstruction, a KL or VQ bottleneck so intermediate points decode to
sound, and auxiliary supervision on the latent.

Training data comes from a canonicalized memmap built once, since reading the audio dominates every
pass. Augment by resampling within the corpus's own transposition range — an octave at the median,
seventeen semitones at p90 — which supplies free contrastive positives at the same time.

**Must beat PCA on both axes to be adopted**: reconstruction error *and* retrieval. A learned latent
that reconstructs better while retrieving worse has traded away goals 1 and 2 for goal 3, and the
whole argument for one shared space is that it need not.

**Gate:** the comparison table against PCA and against the two descriptors, plus a listening set.

---

## Stage 4 — A better vocoder

**Exists only if Stage 2's listening test says phase is the bottleneck.** Griffin-Lim estimates
phase iteratively and smears transients; on a corpus whose median sound is 0.7 seconds and often a
drum hit, that may or may not matter enough to spend a training run on.

**Delivers:** a learned inverse from the canonical representation to audio, swapped in behind the
same `Vocoder` protocol.

**Must beat:** Griffin-Lim on the same reconstruction metric and the same listening set, with the
codec held fixed.

---

## Stage 5 — A waveform codec

RAVE, or its successors. Explicitly not off the table — deferred until the metrics exist to judge
it, and until the cheap stages have said what "good" means for this corpus.

It implements `SampleCodec` directly, with no canonicalizer and no vocoder, which is why the
protocol was shaped to allow that. On 12 GB it needs a reduced batch size and gradient
accumulation, and it is measured in days rather than hours.

**Must beat:** everything before it, on every metric, or it is an interesting result rather than an
adopted one.

---

## Stage 6 — The morph in the application

**Delivers:** the feature the user actually asked for, reachable from the UI.

A server route that synthesizes on request, and a weight control beside the existing spectral
distance readout — the two-sample gesture already exists, and
[`03-architecture.md`](03-architecture.md) names the two call sites that need generalizing. Decide
then whether to stream or to cache content-addressed.

**Gate:** the user can pick two samples, drag a weight, and hear the result.

---

## Standing rules that apply throughout

- **Real samples for anything that must sound like music.** The dev-library sandbox is for
  exercising pipelines.
- **`pg_dump` before a pipeline run against a catalog worth keeping.** The naming convention and
  the reasoning are in [`07-environment.md`](07-environment.md).
- **Long passes make the machine unusable while they run.** Say how long you expect one to take
  before starting it, and prefer a time when the machine is otherwise free.
- **Experiments stay out of the repository.** The repository holds the machinery — protocols,
  codecs, entry points, the evaluation harness, tests. Runs, metrics and checkpoints live outside
  it. The repository stays clean while the work stays experimental.
