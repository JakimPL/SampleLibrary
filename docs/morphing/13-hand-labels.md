# The hand labels, and how a descriptor is scored against them

The first hand labels arrived on 2026-09-09: 197 samples, labeled in the web interface with a
vocabulary the user built as they went. This document records what that vocabulary looks like, the
policy that reads it, the metric that scores a descriptor against it, and where the two existing
descriptors and a pretrained model stand on it. Nothing here writes to the `curation` schema.

## What the labels look like

| Quantity | Value |
|---|---|
| Labeled samples | 197 |
| Distinct label strings | 80 |
| Distinct tags | 47, of which 32 top-level |
| Samples carrying two or three tags | 89 (45%) |
| Tags one level deep (`HI-HAT: CLOSED`) | 87 uses |
| Tags two levels deep (`PIANO: ELECTRIC: RHODES`) | 1 use |

The tags mix **facets**. Most name a source -- `SYNTH` 39, `STRINGS` 26, `HI-HAT` 27, `CYMBAL` 24,
`BASS DRUM` 21, `SNARE` 18, `PIANO` 12, `BASS` 12 -- and beside them stand an articulation
(`PLUCK` 10, `PAD` 2), harmonic content (`CHORD: MINOR` 6, `CHORD: MAJOR` 5), and production
treatment (`LO-FI` 33, `CHIPTUNE` 9, `REVERB` 7, `REVERSE` 6). A sample is `SNARE, LO-FI` or
`SYNTH: PULSE, CHIPTUNE`: several things at once, at whichever depth the listener cared to state.

Two labels had a comma typed for a colon (`BASS, ELECTRIC`, `BASS, SYNTH`); the user corrected
both. `sampleannotations vocabulary` is what surfaced them.

Against the keyword classifier, the labels agree where a keyword fires -- `cymbal` → `CYMBAL` 18
of 21, `hi_hat` → `HI-HAT` 17 of 26, `kick` → `BASS DRUM` 14 of 21 -- and disagree often enough to
matter: four samples the keyword table calls `hi_hat` are strings. Half of the labeled samples are
ones no keyword reached at all.

## The policy

1. **A label is a set of tag paths.** Commas separate tags; colons step a tag from a broad
   category to a specification. `SYNTH: PULSE, CHIPTUNE` is `{(SYNTH, PULSE), (CHIPTUNE)}`.
2. **A path is a tag's identity.** `ELECTRIC` under `BASS` and under `GUITAR` are two tags: a
   specification means something only under its category.
3. **A path asserts its ancestors.** `HI-HAT: CLOSED` is also `HI-HAT`. The ancestor-closed set is
   what two labels are compared on.
4. **Agreement is the Jaccard overlap of two closed sets**, in `[0, 1]`: `HI-HAT: CLOSED` against
   `HI-HAT: OPEN` is 1/3, against `HI-HAT` is 1/2, against itself is 1; `SYNTH, PLUCK` against
   `SYNTH: PULSE, CHIPTUNE` is 1/4. One scalar serves as graded relevance for scoring and as a soft
   target for training. Reading labels to one level is a parameter, and the default reads them
   whole: a deeper tag only ever adds partial credit to its own kind.
5. **Tags are attributes, never exclusive classes.** No metric asks a sample to belong to one of
   32 classes, and no facet taxonomy exists in code. Every tag with at least five samples is scored
   on its own, which is how `LO-FI` is judged apart from `SNARE` and how "perceptual difference wins
   over categories" stays visible per tag rather than legislated.
6. **Keyword categories stay a separate, weaker source**, kept as their own metric.
7. **Wording is reported, never fixed by a pipeline.** The vocabulary command lists the tree with
   counts, names that stand both as a category and as a specification under another (`SYNTH`,
   legitimately both), and tags carried by one sample.

`samplecore.labeling` implements the reading and the agreement; `samplecloud.evaluation.hand_labels`
the metric.

## The metric

Every labeled sample ranks every other labeled sample by distance in the standardized vector
space, with its own equivalence class left out. Three numbers come out, with their chance levels:

- **NDCG@10**, graded by agreement, over the nearest ten. A bootstrap over the queries gives a 90%
  interval, since 197 queries is few.
- **Precision at one**: whether the nearest labeled neighbor shares any tag.
- **Average precision per tag**, for tags with at least five samples, and their mean.

Chance is read from the same candidates in a random order, so a descriptor knowing nothing scores
it. Coverage travels with the score: 197 of 127,588 is 0.15% of the catalog, and the score will
firm up only as the person labels more.

## Where the descriptors stand

Measured with `samplecloud-evaluate --skip-transposition`, seed 0, labels read whole.

| Embedding | NDCG@10 [90%] | mAP over 24 tags | P@1 | Category macro-F1 |
|---|---|---|---|---|
| `invariant` (experiment 2) | 0.374 [0.350, 0.402] | 0.333 | 0.594 | 0.337 |
| `librosa` (experiment 3) | **0.483** [0.453, 0.514] | **0.384** | **0.690** | **0.468** |
| chance | 0.090 | -- | 0.140 | -- |

`librosa` leads on the hand labels as it leads on the keyword categories, and by about the same
margin. Per tag, both find `CHORD` (0.75 / 0.64), `BASS DRUM: KICK` and `REVERSE` easily; both miss
`LO-FI` (0.22 / 0.28), `REVERB` (0.09 / 0.12) and `FX` (0.04 / 0.14). A treatment is spread across
every source, and neither descriptor was built to hear it.

### A pretrained model, for scale

The same 197 samples embedded by a frozen general-purpose audio-text model
(`laion/larger_clap_music_and_speech`, 512 dimensions, read at the nominal rate), leave-one-out
over the labeled set in a scratchpad, with the prototype of this metric:

| Embedding | NDCG@10 | mAP over 15 top-level tags | P@1 |
|---|---|---|---|
| `invariant` | 0.397 | 0.333 | 0.599 |
| `librosa` | 0.499 | 0.389 | 0.695 |
| **CLAP, frozen** | **0.621** | **0.534** | **0.782** |

A model never shown a tracker sample beats both descriptors by a wide margin on what the user
labeled, and it is nearly rate-invariant within a whole tone (97% rank-1 at ±2 semitones against
a 3,000-sample gallery) while collapsing at the octave the corpus retunes by at the median
(18-40% at ±12). Zero-shot text prompts over the 32 top-level tags land a right tag first 52% of
the time. That is the case for the next two stages: the model as a *teacher* for a descriptor that
reads this project's own canonical grid, where the canonicalizer's alignment supplies the
invariance the teacher lacks.

### The teacher over the whole catalog

The same model as the `clap` backend (`samplecloud --backend clap --extract-only`), 127,588
vectors in experiment 4, scored by `samplecloud-evaluate` with 200 probes, seed 0, beside the two
descriptors from [`11-descriptor-baselines.md`](11-descriptor-baselines.md):

| | `invariant` | `librosa` | **`clap`** |
|---|---|---|---|
| Transposition rank-1, all offsets | **62.9%** | 14.3% | 25.9% |
| Transposition rank-1 at −12 / +12 st | **75.0% / 56.7%** | 0.0% / 1.7% | 11.0% / 8.5% |
| Transposition rank-1 at ±2 st | 80.0% / 81.7% | 78.3% / 75.0% | 76.0% / 76.0% |
| Category accuracy | 0.472 | 0.564 | **0.658** |
| Category macro-F1 | 0.337 | 0.468 | **0.578** |
| Note agreement, pitch count | +0.520 | +0.567 | **+0.632** |
| Single-pitch AUC | 0.730 | 0.768 | **0.799** |
| Hand-label NDCG@10 [90%] | 0.374 [0.350, 0.402] | 0.483 [0.453, 0.514] | **0.609 [0.579, 0.638]** |
| Hand-label mAP over 24 tags | 0.333 | 0.384 | **0.532** |
| Hand-label P@1 | 0.594 | 0.690 | **0.787** |

Every metric read off labels or playing goes to the teacher, by a margin that clears every
interval; the one read off retuning goes to `invariant`, and the teacher's own curve falls from
three quarters at a whole tone to a tenth at an octave. Per category it lifts `vocal` (0.471 →
0.600), `pad` (0.329 → 0.432) and `fx` (0.244 → 0.454), the classes both descriptors had been
weakest on, and it is the first descriptor to find `pluck` at all. The pass over the catalog took
55 minutes, the model's own log-mel picture computed on the device.

## The pilot behind the next stage

3,197 samples (the 197 labeled and 3,000 drawn), canonicalized on the committed log-frequency
geometry and pooled to one band per semitone; one retuned view per sample at a uniform offset in
±12 semitones; the labels split in half, 98 for a training term and 99 held out. A four-stage
convolutional network with global pooling, 512 outputs, 40 epochs, about 80 seconds per variant.
Retuning is rank-1 retrieval among the 3,000, so the shares are upper bounds against the full
catalog.

| Embedding | Held-out NDCG@10 [90%] | Held-out mAP | Rank-1 at −12 / +12 st |
|---|---|---|---|
| teacher, frozen | 0.559 [0.515, 0.600] | 0.530 | 40% / 18% |
| grid PCA-128, no learning | 0.372 [0.337, 0.411] | 0.351 | 2% / 5% |
| student: distill only | 0.548 [0.507, 0.588] | 0.520 | 67% / 28% |
| student: distill + retune contrast | 0.493 [0.451, 0.533] | 0.465 | 90% / 82% |
| **student: distill + retune + 98 hand labels** | **0.559 [0.516, 0.603]** | **0.550** | 88% / 77% |
| student: retune contrast only | 0.426 [0.384, 0.463] | 0.384 | 97% / 93% |

Distillation carries the teacher's agreement onto the grid whole; the retuning term buys the
octave and costs agreement; 98 hand labels buy it back, to the best held-out score of every
variant, with the invariance kept. Self-supervision alone stays near the untrained grid on the
labels. The recipe for the descriptor stage follows from those four rows, and the weight of the
retuning term is the one to sweep.

## Zero-shot suggestions over the catalog (2026-09-12)

The 52% of the scratchpad probe above became a pass. `samplecloud-suggest` reads a `clap`
experiment's vectors, which are unit length, against the text tower's reading of a vocabulary of
prompts (`This is the sound of {label}.`, the label's levels read from the most specific outward,
`HI-HAT: CLOSED` as `closed hi-hat`), keeps each sample's closest three under an experiment of the
`zero_shot` backend, and reports two agreements against the hand labels: exact, the first pick as
written lying in the label's closure, and by category, its category alone lying there. The shipped
vocabulary is 34 instruments in the hand-label grammar, drums first; `hand-labels` ranks the
wordings people wrote instead.

Two readings of the catalog are scored: experiment 4, read at the nominal rate, and a `clap`
experiment read at each sample's playback rate (`samplecloud --backend clap --heard-rate`), since
the teacher's rate invariance ends within a whole tone and a bass played two octaves below its
file's rate reads as a pluck at the nominal rate.

### At the nominal rate

`make cloud-suggest EXPERIMENT=4` wrote experiment 8 over the 127,588 samples in minutes. Against
the 216 hand labels the first pick agrees exactly on 62 (28.7%) and by category on 112 (51.9%),
the share the scratchpad probe had promised. Per hand tag, the category agreement of the first
pick, tags with at least five labeled samples:

| Hand tag | Labeled | By category | Where the rest went |
|---|---|---|---|
| `SNARE` | 18 | 89% | `TOM` |
| `FX` | 5 | 80% | |
| `HI-HAT` | 27 | 78% | `PERCUSSION: SHAKER` 4 |
| `BASS` | 12 | 75% | |
| `PIANO` | 12 | 67% | |
| `PAD` | 6 | 67% | |
| `SYNTH` | 47 | 66% | `BASS: SYNTH` 7, `FX` 4 |
| `CHORD` | 11 | 64% | `SYNTH: LEAD` 3 |
| `CYMBAL` | 26 | 62% | `HI-HAT: OPEN` 7 |
| `BRASS` | 5 | 60% | |
| `REVERSE` | 7 | 57% | |
| `LO-FI` | 34 | 56% | a treatment, so any instrument counts |
| `BASS DRUM` | 21 | 33% | `TOM` 3, `FX` 2 |
| `REVERB` | 9 | 33% | |
| `PLUCK` | 10 | 30% | `BASS: SYNTH` 5 |
| `CHIPTUNE` | 10 | 30% | `FX` 4 |
| `STRINGS` | 31 | 23% | `SYNTH: LEAD` 11, `SYNTH: PAD` 3, `BRASS` 3 |

Drums and bass are named; strings at the nominal rate become synth leads, and a bass drum a tom
or an effect. Over the whole catalog the first pick is `FX` for 23.7% of the samples and
`SYNTH: LEAD` for 11.5%, and `STRINGS` for 0.1%: at the nominal rate the model hears the library
as a bright synthetic place, which is what reading a sample two octaves too high sounds like. Part
of the per-tag misses is wording on both sides: the user's `CONGA`, `SHAKER` and `TAMBOURINE`
against the vocabulary's `PERCUSSION: CONGA` and `PERCUSSION: SHAKER` count as misses here and
are the same thing.

### At the playback rate

The heard-rate scoring follows its run and is recorded here against the same table.
