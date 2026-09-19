# The interpolation critic: does an autoencoder learn to move pitch on its own?

Every morph built so far either crossfades or moves only what it was built to move. PCA and the
conditioned codec interpolate as decibel crossfades, and the envelope route keeps one sound's pitch
content and never glides. [`24-learned-features.md`](24-learned-features.md) names one mechanism
with evidence that a learned model can find a movable feature without being told what it is: ACAI
(Berthelot et al. 2018), a critic that reads decoded latent interpolants and an autoencoder taught
to make them look like sounds. On a one-variable benchmark it made an autoencoder move a line
instead of superimposing two, by a factor of about thirty. It had never been tried on audio.

This document is Step 1 of that note. One autoencoder is trained twice on the library, once with
the critic's term and once without, and both are asked one question whose answer is known:

> Take a sample and the same sample retuned by k semitones. Is the decoded latent midpoint one
> spectrum shifted by k/2, or the two spectra stacked?

It is judged on grids and pictures alone. Audio at full resolution waits for a model that passes.

## The instrument: ladders with a known middle

`morph read-ladders` (`samplemorph.measurement.ladders`) builds **ladders**: nine steps between two
ends whose every intermediate is known.

- **Retuned ladders.** A library sample retuned from −k/2 to +k/2 semitones around its stored pitch,
  for k in {3, 5, 7, 12}, each step rendered through the grid cache's own recipe (resample,
  canonicalize, pool to one band per semitone). One and two semitones are left out: at one band
  per semitone a half-band move and a crossfade look alike.
- **Synthetic ladders.** Harmonic tones under one resonance, with the pitch moving, the resonance
  moving, or both moving in opposite directions.
- **Unrelated pairs.** Two library samples with no known middle, which is what the critic trains on.

Every interior step of a path is placed against four references, each a distance in decibels over
the trusted bands with the common level set aside: the walker's own reconstruction of the true
step, the crossfade of its two reconstructed ends, the nearer reconstructed end, and none of them.
The nearest reference is the step's **verdict**: *moved*, *faded*, *switched*, or *neither* when
every reference stands further than the truth stands from the crossfade. The central steps, at
3/8, 1/2 and 5/8, are the ones read, since near the ends a move and a crossfade are a fraction of
a band apart.

Readings trust only the bands where the analysis window resolves a semitone (from about 760 Hz
up) and leave out the top k bands, which a retuning pushes past Nyquist or pulls empty. A ladder
whose middle stands within 4 dB of its crossfade has nothing to tell apart and is skipped.

Two references calibrate the instrument. The **crossfade** reads 100% faded at every interval.
The **translation oracle** moves the first end's picture along the band axis by the weight's share
of the interval, which is what a perfect mover would decode. On 20 samples it read *moved* at
100%, 100%, 100% and 96% of central steps at 3, 5, 7 and 12 semitones, with a median shift
deviation under 0.1 semitone. Its moved share, the crossfade distance over the sum of both
distances, is only 0.76–0.81, because a band shift stands 3–8 dB from a true retuning on the
pooled axis: the analysis resolves high bands more finely than low ones, and peak normalization
offsets a retuned reading by about 9 dB overall until the common level is set aside. That is why
the verdict, not the share, is the gate.

## The model

`samplemorph.features` holds the networks, `samplemorph.training.features` the training.

- **Autoencoder.** Four stages of two 3×3 convolutions each (the first with stride 2), group norm
  and GELU, over the pooled grid of 113 bands padded to 128 by 64 columns. The deepest map
  (256 × 8 × 4) is flattened into a linear layer to a 128-number latent, so a coordinate can depend
  on where a feature sits. The decoder mirrors it with nearest upsampling and convolutions, and a
  1×1 convolution and a sigmoid return every cell to [0, 1].
- **Critic.** The encoder's stages and a linear layer to one number.
- **Objective.** Every batch is paired with itself rolled by one, and every pair mixed in the
  latent at a share α drawn uniformly in [0, 0.5]. The autoencoder minimizes the multi-scale L1
  reconstruction error plus `critic_weight` times the critic's squared answer on the decoded
  interpolants. The critic minimizes its squared error on α, plus its squared answer on a sound
  mixed 20% into its own reconstruction, which it learns to read as 0.
- **Steps.** Two optimizers, one per network, stepped by hand once a batch each, the autoencoder
  first with the critic held still, each clipped and scheduled on its own. The critic trains in
  both arms, so the plain arm measures how plainly its interpolants show.
- **Data.** The pooled grid cache (137,067 samples, each stored and at two retunings within ±17
  semitones). Each epoch reads every training sample at one of its three views. 5% is held out by
  equivalence class, so a tracker module's copies of a sound never straddle the split, and both
  arms share the split. The ladders are drawn from the held-out samples alone.
- **Export.** The epoch that reconstructs the held-out stored grids best, which means the same in
  both arms. The critic is written beside the autoencoder, with the held-out hashes.

## The run

`runs/features-2026-09-19/run.sh` under the library root: the plain arm (`--critic-weight 0`), the
critic arm (`--critic-weight 0.5`), both with seed 0, 20 epochs, batches of 64, rate 1e-4, on the
GPU; then `morph read-ladders` over 100 held-out samples, 12 synthetic ladders per family and 24
unrelated pairs, through the crossfade, the oracle and both arms, on the processor.

**The prediction, stated before the run.** The library holds chords and octave doublings, so two
pitch contents a fifth or an octave apart can look like one real sound to a critic. If the critic
works, its effect should be strongest at 3 and 5 semitones and weakest at 12.

**The proposed gate.** The plain arm reads as a crossfade. On the 3 and 5 semitone ladders, at
least half of the critic arm's central steps read *moved*, against almost none of the plain arm's;
the critic arm's median shift deviation there is at most 1 semitone; its reconstruction is within
1.5 dB of the plain arm's; and its pictures show a ridge.

## What the training did

| Arm | Time | Held-out reconstruction | Critic's error on held-out interpolants |
|---|---|---|---|
| plain, weight 0 | 49 min | 2.73 dB | 0.0075 |
| critic, weight 0.5 | 67 min | 2.86 dB | 0.035 |

A critic that answered every interpolant with the mean share would score 0.021. In the plain arm
it reads the share well: a plain latent midpoint shows plainly. In the critic arm it scores worse
than that constant answer, so the autoencoder won the game the objective sets. The critic's term
cost 0.14 dB of reconstruction over the whole grid, while over the trusted bands the ladders read
the critic arm's reconstructions 0.3 dB closer (5.24 dB against 5.56): its harmonics above 1 kHz
stay lines where the plain arm's smear.

## What the ladders read

`runs/features-2026-09-19/ladders/` under the library root. 356 ladders were read, 333 retuned
from 100 held-out samples and 23 synthetic, with 24 unrelated pairs; 80 stood too close to their
crossfade to read.

The central steps of the retuned ladders:

| Interval | moved, plain | moved, critic | faded, critic | switched, critic | shift deviation: crossfade / plain / critic / oracle |
|---|---|---|---|---|---|
| 3 | 10% | 46% | 54% | 0% | 1.14 / 0.52 / 0.23 / 0.05 |
| 5 | 2% | 17% | 80% | 2% | 1.87 / 0.83 / 0.61 / 0.05 |
| 7 | 0% | 2% | 91% | 6% | 2.64 / 2.42 / 2.17 / 0.07 |
| 12 | 0% | 1% | 89% | 9% | 4.52 / 4.52 / 4.50 / 0.01 |

The change runs one way. Read step by step on the same ladders, 82 central steps at 3 semitones
went from faded in the plain arm to moved in the critic arm and none went back; at 5 semitones, 36
went over and 2 back. The median distances say the same thing without the verdict: the plain
arm's path stands 0.4–0.6 dB from its crossfade and 1.7–4.2 dB from the truth, while the critic
arm's stands 1.2–1.7 dB from the crossfade, and at 3 semitones about as near the truth (1.3 dB)
as the crossfade (1.2 dB).

The synthetic ladders are few but sharper, since their truth and crossfade stand 9–17 dB apart.
At 3 semitones every central step of the critic arm moved, on the pitch ladders and on the
contrary ones (9 of 9 and 6 of 6), against none of the plain arm's. At 5 semitones two of three
pitch steps moved; at 7 all faded; at 12 they faded or switched. Only three resonance ladders were
readable, all at 12 semitones, and every arm faded on them.

**The shape of the path.** The median tracked shift along the critic arm's path, against the
oracle's straight line:

| Interval | 1/8 | 1/4 | 3/8 | 1/2 | 5/8 | 3/4 | 7/8 |
|---|---|---|---|---|---|---|---|
| 3, critic | 0.20 | 0.49 | 0.91 | 1.41 | 1.95 | 2.34 | 2.77 |
| 3, oracle | 0.25 | 0.86 | 1.04 | 1.49 | 1.94 | 2.12 | 2.73 |
| 5, critic | 0.19 | 0.65 | 1.36 | 2.70 | 3.73 | 4.29 | 4.68 |
| 7, critic | 0.09 | 0.28 | 1.38 | 3.65 | 6.61 | 7.04 | 7.08 |
| 12, critic | 0.04 | 0.13 | 0.59 | 10.34 | 11.87 | 11.98 | 12.00 |

At 3 semitones the critic arm glides. At 5 it holds near the ends and hurries through the middle. At
7 it covers five semitones in two steps, and at 12 it turns over at the midpoint. The pictures show
the same: `pictures/retuned/ae5ab836d522-{3,5,7,12}st.png` draw a slant, an S, a hook and a fade.
The plain arm's shift track bends too, because a blurred crossfade puts the correlation peak between
the ends; its verdicts are still faded, and its pictures show both pitches washed into one band of
color above 1 kHz.

**Between unrelated samples** the critic arm holds nearer one sound and turns over in the middle:
its midpoints depart from the crossfade by 0.18 of the distance between the ends (plain 0.05), and
their spectral spread exceeds the ends' by −0.03 (plain 0.08, crossfade 0.23).

**The critic's own scores.** In the plain arm the critic scores the latent path (0.16–0.28) above
the crossfade of the reconstructed ends (0.10–0.18), and both above a reconstructed sound (0.07):
a plain latent midpoint looks less like a sound than a crossfade does. In the critic arm the path
scores 0.12–0.13, as a sound does (0.12), and the crossfade 0.14–0.16. The critic still marks a
crossfade, by a thin margin, so the null at 12 semitones is not a critic that accepts crossfades.
There the autoencoder satisfies it with a fade that turns over faster than the crossfade and
spreads less (spread excess 0.00 against the plain arm's 0.05), read faded at 89% of central
steps and switched at 9%.

## What bounds the reading

The autoencoders keep a true middle and a crossfade apart by a quarter of what the grids do: the
median distance between a model's reconstruction of the true step and the crossfade of its
reconstructed ends is 1.75–4 dB, against 7–8 dB between the grids themselves. Where that distance
is under 1 dB no path can read as moved. Binned by the lower of the two arms' distances, the steps
where both keep more than 4 dB read moved at 100% in the critic arm at 3 semitones (plain 32%) and
46% at 5 (plain 1%). At 7 and 12 semitones neither arm moves more than 6% of any bin's steps. The
pooled axis and a 2.7 dB autoencoder hide part of what the critic does at short intervals; the
long intervals are not hidden.

## Verdict

Against the gate stated before the run:

- The plain arm reads as a crossfade: **met**, 90–100% faded.
- Half of the critic arm's central steps move at 3 and 5 semitones, against almost none of the
  plain arm's: **missed**, 46% and 17% against 10% and 2%.
- The critic arm's shift deviation there is at most 1 semitone: met (0.23 and 0.61), but the plain
  arm meets it too (0.52 and 0.83), so it separates nothing.
- Reconstruction within 1.5 dB of the plain arm: **met**, 0.14 dB.
- A ridge: at 3 semitones; an S at 5, a hook at 7, none at 12.

The gate is missed on its main term. The prediction held in its order: the effect is strongest at
3 semitones and gone at 12.

What the critic does is make the middle of a path look like one sound. Over short intervals that is
a glide, since a glide is the nearest single sound. Over a fifth it is a quick switch, and over an
octave a quick fade between a tone and its own octave, which is close to one sound already, as the
prediction expected; both cost the autoencoder less than a glide. ACAI's objective has no term
against a switch: the critic reads each point alone, and a switched point is a sound it scores as an
end. So the critic moves features on its own only as far as a move is cheaper than a switch, which
here is about 3–5 semitones.

## Where this stands

Two readings are open, and this run does not decide between them. The first is resolution: at one
band per semitone the ladders read the models through a blur, and where the blur leaves room the
critic arm moves at 3 semitones every time, so full resolution would likely read a higher share
there. The second is the switch past 5 semitones, which shows at every separation the models keep
and which the next model has to rule out by construction or by a term that prices it: a path whose
steps must be evenly spaced in the latent's decoded distance, or the named equivariant coordinates
of Step 2 in [`24-learned-features.md`](24-learned-features.md), which move by construction.
