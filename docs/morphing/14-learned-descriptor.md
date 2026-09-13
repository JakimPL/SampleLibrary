# A descriptor that reads the canonical grid

[`13-hand-labels.md`](13-hand-labels.md) found a pretrained audio-text model leading both
hand-built descriptors on every metric read off labels or playing, and losing the one read off
retuning: it moves under an octave, and the corpus retunes by an octave at the median. This is the
descriptor that keeps what the teacher knows and reads the grid whose alignment removes the
retuning.

## Two models, one interface

The three goals ask for two objects. A **descriptor** says what a sound resembles and is judged by
the evaluation harness; a **code** reconstructs a sound and is judged by listening. Asking one
latent for both spends its capacity on the 160,448 cells a reconstruction has to get right, and
197 labels cannot steer that. So the descriptor is trained on its own, small and fast, and the
codec that comes next conditions on it: label supervision touches the descriptor alone, and a
codec conditioned on a frozen descriptor cannot be degraded by it.

## What it is taught with

Three signals, each a term of one loss (`samplemorph.training.descriptor_losses`):

- **Distillation** from the teacher's vector for the same sample, on the stored reading and on a
  retuned one. This carries what sounds alike to people.
- **Retuning contrast** between the stored reading and a retuned view of the same sound, each
  finding the other among the batch. This carries that a retuning changes nothing.
- **Label contrast** over the labeled samples in the batch: the softmax of a sound's similarities
  to the other labeled sounds is scored against their label agreements, normalized to a
  distribution, so a sound is pulled toward everything sharing a tag in proportion to how much it
  shares. A quarter of the labeled samples is held out and never taught.

The network (`samplemorph.descriptors.grid_descriptor`) reads the canonical grid pooled to one
band per semitone (209 × 64) through four convolutional stages with global pooling, the canonical
duration appended, into a 512-dimensional unit vector matching the teacher's. Half a million
parameters.

## The cache

Every epoch reads the same grids, so the catalog is canonicalized once
(`samplelibrary morph cache-grids`) into a memory-mapped file under the library root: the stored
grid and two retuned views per sample, at offsets drawn uniformly within ±17 semitones, the corpus's
own ninetieth percentile. Pooled and stored at half precision, the whole catalog is 10 GB. The
descriptor is then described over the same cache (`samplelibrary morph embed`), so writing its
vector for every sample costs one forward pass rather than a second canonicalization of the catalog.

## The run

`samplelibrary morph cache-grids --workers 12` took 46 minutes over the catalog. `samplelibrary
morph train-descriptor --teacher-experiment 4 --epochs 12 --workers 4`, the pilot's loss weights
(distillation 1.0, retuning 0.5, labels 0.5), 148 labels taught and 49 held out, 1,326 steps of 128
per epoch, 27 minutes on the GPU under a 16 GB memory ceiling. Validation each epoch reads the 49
held-out labels and a gallery of 1,000 other samples at a fixed retuned view:

| Epoch | Validation loss | Held-out NDCG@10 | Retune rank-1 among 1,049 | Cosine to the teacher |
|---|---|---|---|---|
| 1 | 0.770 | 0.548 | 91.8% | 0.557 |
| 4 | 0.510 | 0.588 | 97.3% | 0.646 |
| 8 | 0.454 | 0.602 | 97.9% | 0.683 |
| 12 | 0.438 | 0.595 | 98.1% | 0.702 |

The loss was still falling at the end, so a longer run is a free experiment; the held-out
agreement had settled by epoch 8.

## Where it stands

`samplelibrary morph embed` wrote its vector for every sample as experiment 6 in seven seconds, and
`samplelibrary cloud evaluate` scored it with 200 probes, seed 0, beside the earlier experiments:

| | `invariant` | `librosa` | `clap` | **`learned`** |
|---|---|---|---|---|
| Transposition rank-1, all offsets | 62.9% | 14.3% | 25.9% | **74.2%** |
| Transposition rank-1 at −12 / +12 st | 75.0% / 56.7% | 0.0% / 1.7% | 11.0% / 8.5% | **83.0% / 72.5%** |
| Transposition rank-1 at −17 / +17 st | 58.3% / 45.0% | 0.0% / 0.0% | 4.0% / 1.5% | **73.5% / 46.0%** |
| Transposition rank-1 at −24 / +24 st | 51.7% / **23.3%** | 0.0% / 0.0% | 0.5% / 0.0% | **53.0%** / 15.5% |
| Category accuracy | 0.472 | 0.564 | **0.658** | 0.652 |
| Category macro-F1 | 0.337 | 0.468 | **0.578** | 0.559 |
| Note agreement, pitch count | +0.520 | +0.567 | +0.632 | **+0.641** |
| Single-pitch AUC | 0.730 | 0.768 | 0.799 | **0.802** |
| Hand-label NDCG@10 over the 49 never taught | 0.327 [0.283, 0.371] | 0.421 [0.367, 0.480] | 0.598 [0.545, 0.655] | **0.631 [0.562, 0.698]** |
| Hand-label P@1 over the 49 never taught | 0.551 | 0.673 | 0.796 | **0.837** |

**Read the hand-label rows with care.** The harness scores all 197 labels, and 148 of them taught
this descriptor, so its harness figure (NDCG 0.855, mAP 0.721) is a fit rather than a test. The
rows above rank only the 49 held-out labels against every other labeled sample, for every
descriptor alike, and that is the number to compare: the student sits where the teacher sits,
inside the interval, with 49 queries too few to say more.

What it settles:

- **One descriptor now does both.** [`11-descriptor-baselines.md`](11-descriptor-baselines.md)
  found each hand-built descriptor winning the half it was built for. The student beats
  `invariant` on retuning at every offset up to seventeen semitones, holds the median rank at one
  through two octaves down, and keeps the teacher's agreement with categories, playing and hand
  labels. The one place `invariant` still leads is two octaves up, where a retuned reading keeps a
  fifth of its frames.
- **The invariance came from the grid, and the meaning from the teacher.** The pilot showed
  distillation alone lifting octave retrieval from 40% to 67% before any retuning term, which is
  the alignment doing its work; the retuning term takes it the rest of the way.
- **`LO-FI` is the tag the student learned most from the labels**: 0.253 for the teacher against
  0.609 for the student over all 197, and it is a treatment no descriptor could hear before. Read
  it as what 33 labeled examples of a treatment teach a network that already knows sources.

The descriptor is `models/descriptors/descriptor.pt` under the library root, the run is recorded
under the `descriptor` experiment of the tracking store, and experiment 6 holds its vectors.
Promoting it to the cloud is `samplelibrary cloud embed --backend learned --model descriptor
--experiment-id 6 --limit 0`, left to the user.

## What stays open

- **The retuning weight.** The pilot saw it trade agreement for invariance; this run used the
  pilot's 0.5 and both came out well. A sweep over 0.25 and 1.0 is two more half-hour runs.
- **Longer training.** The loss had not reached its floor at twelve epochs.
- **Two octaves up.** A short sample retuned by +24 semitones analyzes to very few frames, and the
  cache's views reach only ±17. Drawing a share of views further out would say whether that is
  a limit of the grid or of what the network was shown.
- **Whether this is the space the codec should decode from.** That is the next stage.
