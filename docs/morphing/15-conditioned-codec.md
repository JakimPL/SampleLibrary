# A codec that decodes from the descriptor

[`14-learned-descriptor.md`](14-learned-descriptor.md) left the space that carries similarity
and the labels, and the question of whether a codec should decode from it. This is that codec: a
convolutional autoencoder of the canonical grid whose every stage is told what the sound is by the
descriptor's vector, with a small residual under a Gaussian prior for what the descriptor leaves
out. A morph moves the descriptor half of the latent through the space the harness judges and the
residual half through a space with a prior, and decodes from both.

## What it is

`samplemorph.codecs.conditioned_model`: four convolutional stages each striding the band axis by
four, the time axis by one then two, every stage modulated by the descriptor (a scale and a shift
per channel), down to a bottleneck of 128 channels over 10 bands and 8 columns, read into a
64-dimensional residual as mean and log-variance; a mirrored decoder from the residual and the
descriptor back to the 2,507 × 64 grid. 7.8 million parameters. The 512-dimensional descriptor
rides along frozen and reads the pooled grid itself, so one cache serves both.

Three terms (`samplemorph.training.codec_losses`):

- **Reconstruction**: mean absolute error over the grid, read at its own resolution and at two
  coarser ones, so the decoder is scored on the shape of a spectrum as well as on its lines.
- **Prior**: the residual's divergence from the unit Gaussian, weighted 0.01 and warmed up over
  2,000 steps so the decoder learns to reconstruct before the residual is asked to stay near the
  prior.
- **Cycle**: the decoded grid, read by the frozen descriptor, must describe as the descriptor it
  was decoded from, weighted 0.1. This is what makes the decoder use its conditioning.

`samplemorph.codecs.conditioned.ConditionedCodec` behind the `SampleCodec` protocol: `encode`
describes the image and reads the residual's mean; the latent is the descriptor followed by the
residual, so the existing `LinearMorpher` runs through both; `decode` brings the descriptor half
back to unit length and rebuilds the grid. `render --model conditioned` reaches it by name from
the weight store beside the array store the linear codecs use.

## The run

`samplemorph cache-grids --cache codec --samples 30000 --bands-per-semitone 12 --views 0`
canonicalized a 30,000-sample draw at full resolution in three minutes, 9.6 GB.
`samplemorph train-codec --cache codec --descriptor descriptor --epochs 15 --workers 4` ran 890
steps of 32 per epoch, 3.5 minutes an epoch, 52 minutes in all under the 16 GB ceiling, 5% of the
draw held out:

| Epoch | Validation loss | Reconstruction | Prior, nats per dimension | Cycle |
|---|---|---|---|---|
| 1 | 0.0546 | 0.0322 | 1.42 | 0.081 |
| 3 | 0.0401 | 0.0274 | 0.67 | 0.059 |
| 8 | 0.0345 | 0.0245 | 0.57 | 0.046 |
| 15 | 0.0330 | 0.0234 | 0.55 | 0.041 |

## Where it stands

Measured on 60 probes drawn outside the codec's training draw (seed 7, 4,000 to 200,000
frames), against the 256-component linear codec fitted on the same grid, both restored through
the same canonicalizer and made audible two ways: handed the source's own phase, and through the
learned phase vocoder from [`12-learned-vocoder.md`](12-learned-vocoder.md). Unrelated samples sit
20.35 dB apart on this probe.

| Codec | Own phase, median | p90 | Learned phase, median | p90 |
|---|---|---|---|---|
| Linear, 256 components | **6.00 dB** | 8.25 | **8.62 dB** | 10.61 |
| Conditioned, 64-dimensional residual | 7.28 dB | 9.63 | 9.49 dB | 11.56 |

**The conditioned codec reconstructs 1.3 dB worse than the linear one.** The gate in the plan
asked for parity, and it is not met: a 64-dimensional residual under a prior carries less of a
particular grid than 256 free components fitted to carry exactly that. This is the fidelity the
prior costs, and it is what the residual size and the prior's weight trade against.

What the linear codec cannot do is the reason the conditioned one exists. Four labeled pairs,
morphed at five weights through each codec, measured by `samplemorph.measurement.plausibility`
with the two readings added for this stage -- each step's energy over the mean of the endpoints',
and its spectral spread over the wider endpoint:

| Pair | Codec | Energy share along the path, 0 → 1 | Spread excess, widest step |
|---|---|---|---|
| snare vs lo-fi snare | linear | 1.82 · 0.69 · **0.35** · 0.22 · 0.18 | −0.14 |
| | conditioned | 1.79 · 1.29 · **0.80** · 0.43 · 0.21 | −0.09 |
| piano vs strings | linear | 0.10 · **0.02** · **0.03** · 0.17 · 1.90 | +0.05 |
| | conditioned | 0.04 · 0.16 · **0.68** · 1.33 · 1.96 | 0.00 |
| kick vs pad | linear | 1.89 · 0.38 · **0.16** · 0.10 · 0.11 | 0.00 |
| | conditioned | 1.86 · 1.21 · **0.31** · 0.19 · 0.14 | 0.00 |
| electric bass vs synth pluck | linear | 1.34 · 0.78 · **0.55** · 0.49 · 0.66 | 0.00 |
| | conditioned | 1.34 · 1.48 · **1.33** · 0.94 · 0.66 | 0.00 |

Every path is monotone through both codecs, and no step spreads wider than its endpoints, so
neither codec plays two sounds at once. The difference is in the energy column. **A straight line
through a grid of decibels thins out whatever the two sounds do not share**: halfway from a piano
to a string section, the linear codec keeps three percent of the endpoints' energy -- the path
passes through near-silence -- and halfway from a kick to a pad, a sixth. The conditioned codec
carries 68% and 31% through the same midpoints, and holds the whole path between the bass and the
pluck at or above the endpoints' own level. The prior on the residual and the decoder's
conditioning are doing what they were put there for: a point between two latents decodes to a
sound with a level, rather than to the shadow of both.

Whether that sound is *between* the two is the question only listening answers. The four pairs
are rendered through both codecs and the learned phase vocoder under
`listening/codec-2026-09-09/<pair>/<codec>/` beside the library, with the originals, the
reconstructions and the three morphs in each. That is the set to judge this stage on.

## What stays open

- **Fidelity against the linear codec.** The 1.3 dB gap is where the residual size and the
  prior's weight trade; a wider residual is the first thing to measure.
- **The decoder's sharpness.** A decoder scored by absolute error produces the average of what it
  is unsure of; if listening finds the reconstructions or the midpoints smeared, an adversarial
  term on the grid is the named follow-up, on the same interface.
- **Which half to move.** The morpher moves the descriptor and the residual at one weight; moving
  them separately -- timbre at a fixed realization, or the reverse -- is a `MorphWeights` field
  away, and the listening set decides whether it is wanted.
