# Teaching a vocoder the phase a magnitude carries

[`10-listening-corrections.md`](10-listening-corrections.md) closed the non-learned path: the
representation clears the listening bar when it is carried by the source's own phase, and every
phase estimate tried under it does not. This is what replaces the estimate.

## The problem is phase, and only phase

Rung by rung, the ladder puts the whole remaining gap on one step. At 144 bands per octave the
representation costs 2.2 to 3.5 dB with true phase, which listening accepted; Griffin-Lim adds 3.8
to 4.5 dB on top, which listening rejected. So the target is not a vocoder that synthesizes audio
from nothing -- it is a model that says what phase belongs with a magnitude of this kind.

That framing decides the shape of the work, and it is much smaller than the alternative. A neural
vocoder trained to produce waveforms has to be told what a plausible waveform sounds like, which is
why the field trains them adversarially. A model asked only for phase has a supervised target: every
sample in the catalog carries its own true phase, and the magnitude the pipeline produces from that
same sample is exactly what the model will meet at inference. Nothing has to be invented, only
learned.

## What a magnitude does and does not determine

The first attempt regressed the phase directly and learned nothing at all: the phase term sat at
2.0, which is what two unrelated points on the unit circle average, and stayed there.

The reason is that the target was not a function of the input. Delaying a waveform by a fraction of
one sample turns every phase in the spectrogram and moves no magnitude worth speaking of, so a
magnitude fixes its signal's phase only up to one angle shared by the whole picture. Asking a model
for the absolute angle asks it to guess a quantity its input does not contain, and the best it can do
is answer the average, which is what it did.

What a magnitude does determine is how the phase *advances* -- from one frame to the next, and from
one bin to the next. Those differences are what an analytic phase-gradient method integrates, and
they are invariant to the shared angle. Supervising them turns the task into one that has an answer:
the loss compares the predicted advance against the true advance along both axes, weighted by the
quieter of the two bins each difference spans, since a bin holding nothing carries an angle no
listener can hear.

An advance that is right everywhere fixes the whole field but for that one constant, and that
constant is inaudible. With that change the loss moved on the first run.

## What the model is held against

The target waveform is the pipeline's own magnitude carried by the source's true phase -- the ladder
rung listening already accepted. Holding the model against that, rather than against the untouched
original, asks it for the phase this grid's magnitude deserves rather than asking it to restore what
the grid discarded. Those are two different jobs, and only the first is needed.

Beside the gradient term, a multi-resolution spectral loss reads both waveforms back through three
window lengths. Phase that no signal could carry shows up there rather than in the magnitude it was
read from: making it audible and analyzing the result reveals the disagreement, at whichever window
length it lives.

## The network

Frequencies enter as channels of a convolution over time, so each output channel reads the whole
spectrum at once while its kernel reads a span of frames. That matches where the structure sits: a
bin's phase is decided by its own recent history and by what the rest of the spectrum is doing at
that moment. Dilations widen the temporal view geometrically, reaching a whole note's worth of frames
at a small cost.

The output is a point on the unit circle per bin per frame rather than an angle, so the network never
has to learn that its largest value and its smallest are neighbors.

The input is read in decibels against each example's own peak, since a sample's level says nothing
about its phase and a quiet sample should present the same picture as a loud one.

## The turning a convolution cannot invent

Supervising the gradients made the loss move, and it stalled early. The reason is the same class of
mistake as before, one step further in.

A bin advances by a fixed angle each hop, set by the analysis window alone -- with a 2,048-point
window stepping 256 frames, a bin's phase comes back round every 8 frames. A convolution reads the
same way wherever it is placed along time, so its output shifts when its input shifts and does
nothing else. It therefore cannot produce a field that turns at a rate depending on where in the
signal a frame sits, which is precisely what the correct answer does. The network was being asked
for something its own structure could not express.

Handing it that turning as two further channels to read makes the answer expressible: what remains
for the model to find is how far each bin departs from the nominal advance, which is what the sound
decides. Measured against the same samples, the same seed and the same epoch:

| | without the turning | with it |
|---|---|---|
| Validation, total | 1.4551 | **1.2103** |
| Validation, phase gradient | 0.8857 | 0.8674 |
| Validation, spectral | 0.5693 | **0.3429** |

The gradient term barely moves and the spectral term falls by 40%. That split says what the change
did: the model was already learning roughly how phase advances, and it could not turn that into
audio that holds together until it was given the reference to advance against.

## The delay a crop cannot know about

Supervising the gradients left the phase term stuck around 0.85 wherever the run went. The reason is
the same shape of mistake once more, and this one had a measurable price.

A crop taken from partway through a recording carries the phase of the whole recording, which is the
phase from its beginning turned by however many frames were skipped. That turning is a pure delay:
no listener hears it. The model, told only the turning counted from its own crop's first frame, has
no way to know it, and the frequency half of the gradient loss charged for it anyway. Measured
against a real tone, a crop three frames along costs **1.707** for a phase that is perceptually the
one it was asked for.

Passing each crop's own starting frame through to the turning removes the charge: the model is asked
for the phase its example really has, rather than for one it has no way to know.

The correction turned out narrower than the size of that number suggests. Roughly seven crops in ten
come from samples shorter than the crop itself, which start at the beginning and rest against silence
for the remainder, so the charge only ever fell on the other three. The fix is right and the term did
not move much for it.

## Griffin-Lim will not refine what the model produces

The obvious next thought is to hand the model's answer to Griffin-Lim as a starting point, letting
one supply structure and the other consistency. Measured over 40 samples the training draw never
saw, iterating from the model's phase makes it monotonically worse:

| Phase | Median | p90 |
|---|---|---|
| The source's own | 3.07 | 4.75 |
| The model's | **6.81** | **8.72** |
| The model's, then 4 iterations | 6.92 | 9.12 |
| The model's, then 16 | 7.27 | 9.42 |
| The model's, then 32 | 7.40 | 9.61 |
| Griffin-Lim from random, 32 | 7.55 | 9.26 |

Every iteration pulls the answer back toward the one Griffin-Lim would have reached alone. The model
is not producing a rough version of a consistent phase that projection would clean up; it is
producing something better than any consistent phase available, and consistency is what costs it.
That also says what the earlier ladder was really showing: the artifact is what a consistent phase
sounds like when the magnitude admits none, so a method whose whole definition is consistency cannot
escape it.

The model's own phase advance is meanwhile *worse* than Griffin-Lim's -- 0.726 against 0.413 on the
same probes -- while its audio is better. It gets the large structure right and the local advance
wrong, where Griffin-Lim does the reverse.

## What it costs

Deriving one training example -- reading the audio, canonicalizing it, restoring it, and reading it
onto the Fourier grid -- takes 44 ms, so the whole catalog is about 1.5 hours of one core. Training
steps run far faster than that: at 32 crops of 128 frames the GPU takes about 33 ms a step, which is
980 crops a second, against about 270 a second that twelve worker processes can derive. The pipeline
therefore runs inside the loader's own workers rather than being precomputed, which also keeps the
training material exactly current with the canonicalizer: a change to the grid changes what the
loader yields, with nothing stale to invalidate.

The first runs went at 31 examples a second across twelve workers, far below what one core manages
alone, because each worker was spreading its own linear algebra across every core the machine has and
a dozen of them were colliding over the same 24. Held to one thread each and raised to twenty
workers, the same pass runs at 136 a second: an epoch over 5,700 samples fell from 190 seconds to 42,
and the quality per epoch is unchanged. That is what makes training over the whole catalog possible
rather than over a draw of a few thousand.


## Where it stood before the long run

Six epochs over 6,000 samples, measured on 40 samples the training draw never saw:

| Phase | Median | p90 |
|---|---|---|
| The source's own | 3.07 | 4.75 |
| The model's | 6.81 | 8.72 |
| Griffin-Lim's | 7.57 | 9.70 |

The model beats Griffin-Lim by 0.76 dB of a 4.5 dB gap, which is a sixth of the way. That is a small
model trained briefly, and the fixes above landed after it, so it says the approach works rather than
that it is finished. What it does not say is whether the remaining distance closes with training:
that is what the long run over the whole catalog is for, and it is a question listening answers
rather than this table.
