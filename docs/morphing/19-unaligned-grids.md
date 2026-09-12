# Unaligned grids, and the codec's fidelity on the probes

The listening review of the chain rebuilt on the fundamental anchor
([`16-pitch-anchor.md`](16-pitch-anchor.md), the set under `listening/codec-2026-09-12/`) ended in
a verdict on the codec rather than on the anchor: given the choice the user would take the linear
codec and be unhappy with both. The conditioned codec "throws a lot of information away", which
makes it poor with chords and percussive samples, "as if it was tried really hard to treat all
samples like tonal", and it adds a vocoder-like effect that takes the clarity away. Percussive
samples are as important as tonal ones. The decision that followed: put the reconstruction's
quality first, and take the pitch anchor out of the grid, since an anchor serves tonal sounds and
the pitch swing it fixes is a quirk to deal with later. This document records the rebuild on
unaligned grids, what it cost the descriptor, and where the codec stands on a fidelity reading
that is now a command.

## What changed in the representation

`Anchor.NONE` is the default of every geometry (`samplemorph.geometry.DEFAULT_ANCHOR`). A grid is
the analysis's bands as they are: 2,708 bands by 64 columns at 288 bands per octave, where the
aligned grid was 5,012 bands with headroom for the shift; the translation conditioner is zero and
stays in the picture as the field an anchoring rule fills. The loudest-band and fundamental rules
remain options on every command (`--anchor`, `ANCHOR=` on the make targets), and a stored model,
cache or descriptor still names the anchor its grids were made with, so nothing built on an
aligned grid is read as unaligned by mistake. The restorer needs no rebuild: it was trained on the
analysis's own bands, which no anchor touches.

Without alignment, a rate change moves a sound's picture up or down the band axis, and a morph
between two pitches moves through the blend of the two pictures. The descriptor is taught that
invariance from retuned views of every grid, as before; the codec is not, and a morph between a
bass at two pitches will pass through both. That is the quirk accepted for now.

## The chain

`runs/unaligned-2026-09-12/run_chain.sh`, on 2026-09-12 from 13:12 to 16:00, each step a make
target under its memory scope:

| Step | Command | Time |
|---|---|---|
| Linear codec | `morph-fit` | 5 min |
| Descriptor cache, 127,588 grids pooled to one band per semitone with views | `morph-cache-grids WORKERS=12` | 69 min |
| Descriptor, distilled from experiment 4 | `morph-train-descriptor TEACHER=4` | 50 min |
| Codec cache, 30,000 grids at full resolution | `morph-cache-grids CACHE=codec SAMPLES=30000 BANDS=24 VIEWS=0` | 5 min |
| Codec, 512-dimensional residual, prior 0.001 | `morph-train-codec CODEC=conditioned-r512 RESIDUAL=512 PRIOR=0.001 BATCH=16` | 34 min |
| Fidelity of the three models on the twelve probes | `morph-measure` three times | 1 min |
| The catalog described, experiment 9 | `morph-embed` | 1 min |
| Evaluation of experiment 9 | `evaluate-fast` | 3 min |

The descriptor cache took an hour longer than the aligned one had, because the retuned views of an
unaligned grid are computed rather than translated. One correction rode along: a retuned view now
records its sample's own canonical duration, where it had recorded the view's, so the descriptor's
duration conditioner reads the same number for a sound however it is retuned.

## What the anchor was worth to the descriptor

Experiment 9, the unaligned descriptor, beside experiment 7, the one on the fundamental anchor,
both by `samplecloud-evaluate --skip-transposition` with 200 probes at seed 0:

| | Experiment 7, fundamental anchor | Experiment 9, unaligned |
|---|---|---|
| Category accuracy | 0.668 | 0.665 |
| Category macro-F1 | 0.583 | 0.580 |
| Single-pitch AUC | 0.808 | 0.808 |
| Hand-label NDCG@10 | 0.874 | 0.869 |
| Hand-label mAP over 26 tags | 0.708 | 0.704 |
| Hand-label P@1 | 0.954 | 0.940 |

Level on every row. The hand-label figures of both are optimistic, since the descriptor is trained
with the hand labels as one of its terms and the evaluation reads the same labels back; they are
comparable between the two runs, which is what they are here for. The alignment bought the
descriptor nothing it could not learn from the views, so the anchor's only remaining case is the
pitch of a morph, deferred by decision.

## The fidelity reading

`samplemorph measure` (`make morph-measure MODEL=<name> HASHES=<file> OUTPUT=<directory>`) takes
a set of probes through a stored codec and the restored vocoder, matches every reconstruction's
loudness to its original's, writes both beside each other under the output directory, and reads
what the reconstruction costs: the held-out spectrum distance in decibels, the modulation distance
and the signed fluctuation, roughness and modulation excesses from
[`18-perceptual-readings.md`](18-perceptual-readings.md), and the loudness and peak after
matching. `MODEL=identity` sends the grid through the vocoder alone, which is the floor every codec
sits above. The medians per sound type are logged and the rows written to `readings.csv`.

The twelve probes of `runs/unaligned-2026-09-12/probes.txt` are the samples the codec review
listened to, seven read as percussive and five as tonal. Medians, all probes then percussive then
tonal:

| Model | Held-out dB | Modulation distance | Modulation excess | Fluctuation excess |
|---|---|---|---|---|
| Identity, the vocoder alone | 4.40 · 4.22 · 4.59 | 0.125 · 0.147 · 0.103 | +0.010 · +0.012 · +0.005 | +0.002 · +0.002 · +0.000 |
| Linear, 256 components | **10.78** · **10.91** · 10.64 | 0.378 · 0.415 · **0.291** | **+0.062** · **+0.100** · **+0.009** | **+0.027** · +0.049 · +0.010 |
| Conditioned, 512-dimensional residual | 13.07 · 14.70 · **10.20** | **0.369** · 0.445 · 0.310 | +0.185 · +0.214 · +0.115 | +0.038 · **+0.041** · +0.010 |

**The conditioned codec loses to the linear one, and where the ear said it does.** On the held-out
distance it is behind on eleven of the twelve probes, by four decibels at the percussive median,
and level with it at the tonal median. Its modulation excess is three times the linear codec's
overall and twelve times on tonal material: the decoded grids carry a modulation the originals
lack, which is the vocoder-like effect the review heard. The bar for this stage was a codec at
least as good as the linear one on percussive and tonal material both, and the vector residual at
512 dimensions under a light prior clears neither. [`15-conditioned-codec.md`](15-conditioned-codec.md)
found the residual's size was not the lever at 64 against 128; at 512 it still is not.

What the layout of that residual does explains the readings better than its size. The bottleneck
holds 128 channels over 11 bands and 8 columns, and the vector residual reads the whole map
through one linear layer into 512 numbers and writes it back through another: every residual
number speaks for every band at every moment, and a decoder rebuilding a transient or a chord's
voicing from that has to put it back where the descriptor suggests. The follow-up is a residual
that keeps the map, `--layout map` on `train-codec` (`LAYOUT=map`): a few numbers at each of the
88 bottleneck cells, read and written through 1×1 convolutions with the descriptor laid over
every cell, so a residual number speaks for the bands and the moment it sits at. Eight numbers
per cell make a residual of 704, close to the vector's 512, with the locality the vector lacks.
Beside it, the cycle term at a tenth of its weight, since a decoder asked to describe as its
descriptor is a decoder pulled toward its category's prototype. Both are queued in
`runs/unaligned-2026-09-12/run_c2.sh`, measured on the same probes, and their rows belong in the
table above.

## What follows

- The map layout's and the cycle knob's readings, on the same twelve probes, against the bar.
- Eight standard pairs (`runs/unaligned-2026-09-12/pairs.json`: two pairs each of basses, kicks,
  snares and chords, the two of a pair heard at the same rate), rendered through the best codec
  and the linear one into `listening/pairs-2026-09-12/`, with the blend, energy, spread and pitch
  readings per step, for the user's verdict.
- Promotion of experiment 9 to the cloud is the user's call; the cloud shows experiment 7 until
  then, and the two are level on every measured row.
