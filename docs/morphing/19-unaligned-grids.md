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
remain options on every command (`--anchor`), and a stored model,
cache or descriptor still names the anchor its grids were made with, so nothing built on an
aligned grid is read as unaligned by mistake. The restorer needs no rebuild: it was trained on the
analysis's own bands, which no anchor touches.

Without alignment, a rate change moves a sound's picture up or down the band axis, and a morph
between two pitches moves through the blend of the two pictures. The descriptor is taught that
invariance from retuned views of every grid, as before; the codec is not, and a morph between a
bass at two pitches will pass through both. That is the quirk accepted for now.

## The chain

`runs/unaligned-2026-09-12/run_chain.sh`, on 2026-09-12 from 13:12 to 16:00, each step under its
memory scope:

| Step | Command | Time |
|---|---|---|
| Linear codec | `morph fit` | 5 min |
| Descriptor cache, 127,588 grids pooled to one band per semitone with views | `morph cache-grids --workers 12` | 69 min |
| Descriptor, distilled from experiment 4 | `morph train-descriptor --teacher-experiment 4` | 50 min |
| Codec cache, 30,000 grids at full resolution | `morph cache-grids --cache codec --samples 30000 --bands-per-semitone 24 --views 0` | 5 min |
| Codec, 512-dimensional residual, prior 0.001 | `morph train-codec --codec conditioned-r512 --residual-size 512 --prior-weight 0.001 --batch 16` | 34 min |
| Fidelity of the three models on the twelve probes | `morph measure` three times | 1 min |
| The catalog described, experiment 9 | `morph embed` | 1 min |
| Evaluation of experiment 9 | `cloud evaluate --skip-transposition` | 3 min |

The descriptor cache took an hour longer than the aligned one had, because the retuned views of an
unaligned grid are computed rather than translated. One correction rode along: a retuned view now
records its sample's own canonical duration, where it had recorded the view's, so the descriptor's
duration conditioner reads the same number for a sound however it is retuned.

## What the anchor was worth to the descriptor

Experiment 9, the unaligned descriptor, beside experiment 7, the one on the fundamental anchor,
both by `samplelibrary cloud evaluate --skip-transposition` with 200 probes at seed 0:

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

`samplelibrary morph measure --model <name> --hashes <file> --output <directory>` takes
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
| Conditioned, map residual, 8 per cell | 12.44 · 13.20 · 11.45 | 0.438 · 0.461 · 0.378 | +0.223 · +0.245 · +0.200 | +0.051 · +0.053 · +0.037 |
| The same, cycle term at 0.01 | 13.65 · 14.10 · 12.61 | 0.460 · 0.497 · 0.388 | +0.243 · +0.259 · +0.127 | +0.066 · +0.067 · +0.058 |

**Every conditioned codec loses to the linear one, and where the ear said it does.** The vector
residual is behind on the held-out distance on eleven of the twelve probes, by four decibels at
the percussive median, and level at the tonal median. Its modulation excess is three times the
linear codec's overall and twelve times on tonal material: the decoded grids carry a modulation
the originals lack, which is the vocoder-like effect the review heard. The bar for this stage was
a codec at least as good as the linear one on percussive and tonal material both, and none of the
three clears it. [`15-conditioned-codec.md`](15-conditioned-codec.md) found the residual's size
was not the lever at 64 against 128; at 512 it still is not.

The second turn moved the residual's layout instead of its size. The bottleneck holds 128
channels over 11 bands and 8 columns, and the vector residual reads the whole map through one
linear layer into 512 numbers and writes it back through another, so every residual number
speaks for every band at every moment. `--layout map` on `train-codec` (`LAYOUT=map`) keeps the
map: a few numbers at each of the 88 bottleneck cells, read and written through 1×1 convolutions
with the descriptor laid over every cell, so a residual number speaks for the bands and the
moment it sits at. Eight per cell make 704 numbers, close to the vector's 512, with the locality
the vector lacks. Measured, the map buys a decibel and a half on percussive material and costs
one on tonal, loses to the linear codec on all twelve probes, and adds more modulation than the
vector did; its validation error on the grid is higher too (0.026 against 0.021). The cycle term
at a tenth of its weight, tried on the map in the same run, makes every reading worse. Locality
at the bottleneck is not what the decoder lacks either.

What the three runs have in common is the shape of the decoder: eight columns rebuilt to
sixty-four through transposed convolutions whose kernels equal their strides, with nothing from
the encoder's finer stages reaching them, and a loss that scores the grid by absolute error. A
decoder like that puts a transient where its block boundary falls and paints what it is unsure
of as the average of its kind; the modulation excess, which rises with every variant that
reconstructs worse, is the sound of that. The linear codec has no such decoder: its
reconstruction is the grid projected onto 256 directions, exact where those directions reach and
smooth elsewhere, and it never adds what the grid lacks.

## The standard pairs

The review had asked for plainer pairs than the first set's: two sounds of one kind at one
rate, so that a morph has only the sound to change. `runs/unaligned-2026-09-12/pairs.json` holds
eight, two each of basses, kicks, snares and chord stabs, drawn by name and by kind from
different modules with a guard against copies of one sample. They are rendered through the
vector codec, the map codec and the linear one into `listening/pairs-2026-09-12/<pair>/<model>/`,
with the originals, the reconstructions and the morphs at 0.25, 0.5 and 0.75, and the readings of
[`15`](15-conditioned-codec.md) on the decoded grids. The least share of the endpoints' energy an
interior step keeps, and the smallest distance of a step from the crossfade of the endpoint grids:

| Pair | Linear, energy | Vector, energy | Map, energy | Vector, blend | Map, blend |
|---|---|---|---|---|---|
| Two slap basses | 0.42 | 0.43 | 0.45 | 0.05 | 0.07 |
| Two short basses | 0.89 | 0.99 | 1.01 | 0.11 | 0.15 |
| Two kicks | 0.19 | 0.58 | 0.99 | 0.09 | 0.14 |
| Two more kicks | 0.48 | 0.60 | 0.64 | 0.05 | 0.06 |
| Two snares | 0.21 | 0.29 | 0.32 | 0.14 | 0.18 |
| Two more snares | 0.40 | 0.52 | 0.57 | 0.07 | 0.10 |
| Two chord stabs | 0.60 | 0.56 | 0.82 | 0.07 | 0.11 |
| Two more chord stabs | 0.56 | 0.85 | 1.04 | 0.08 | 0.11 |

Every path is monotone through every codec, and no step spreads wider than its endpoints. The
linear codec's paths are crossfades, as they are by construction, and thin out in the middle
where the two sounds differ, to a fifth of the endpoints' energy between the two kicks; the
conditioned codecs keep the middle full, the map codec most of all, and stand a tenth of the
endpoints' own distance away from the crossfade at their closest. That is the case for a learned
decoder, made on material where the linear codec's midpoint is the shadow of both sounds. What
each codec costs the endpoints is what the fidelity table says, and whether a full middle at
that cost is a sound worth having is the user's verdict, in `verdicts.csv` beside the files.

## What follows

- The user's verdict on the standard pairs, and on the reconstructions in the fidelity set.
- The decoder's shape is where the fidelity readings point, and the linear codec is the one
  reconstruction that never adds what the grid lacks. A learned decoder that starts from the
  linear reconstruction and corrects it, the way the restorer corrects the band inverse, keeps
  the linear codec's fidelity as its floor and puts the learning where the crossfade thins out.
  Before that, the linear codec's own ceiling is a five-minute fit away: `samplelibrary morph fit
  --latent-size 1024` says how much of the gap to the vocoder is the 256 components.
- Promotion of experiment 9 to the cloud is the user's call; the cloud shows experiment 7 until
  then, and the two are level on every measured row.
