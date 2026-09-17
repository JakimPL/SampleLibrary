# The envelope morph: one excitation under a moving envelope

A morph between two pitched sounds keeps failing in the same place: its middle plays *two* pitch
contents at once. A crossfade holds both chords and dissolves between them. A route that moves
partials sends some of a note's harmonics travelling and leaves others standing, so the midpoint
sounds two unaligned tones that neither end contains. Every attempt to decide which partials
belong together, by harmonic series or by common fate, moved the problem rather than removing it;
[`21-partials.md`](21-partials.md) and [`22-correspondence.md`](22-correspondence.md) record those
attempts.

This document describes the route that answers the failure by splitting a sound differently, and
what it does and does not give.

## The idea

A spectrum can be read as two things multiplied together:

- the **envelope**: the smooth shape of loudness over frequency, the resonances of a body, the
  brightness of a tone, the balance between registers;
- the **excitation**: what sounds under that shape, the fine structure of harmonics, the noise
  between them, and the silence where there is nothing.

Pitch lives in the excitation. Timbre, to a large part, lives in the envelope. So the route moves
only the envelope, from the first sound's to the second's, and keeps the excitation of *one* sound
whole under it. A chord under a half-way envelope is still that chord, played by something between
the two instruments, and the midpoint never holds two pitch contents.

## How it works

For a weight between 0 and 1:

1. **Alignment.** Both sounds are aligned in time by the transport's time map
   ([`20-audio-transport.md`](20-audio-transport.md)), so the attack of one meets the attack of
   the other and each body is read through its own mass over time.
2. **Reading.** Both analyses are read along that map, frame by frame, as magnitudes.
3. **Splitting.** Each read magnitude is split into an envelope and an excitation. The envelope is
   the loudness over frequency, in decibels, drawn by its first `coefficient_count` cosine
   coefficients alone (a cepstral smoothing), read down to `floor_db` under the sound's loudest
   bin. The excitation is the magnitude divided by that envelope.
4. **The envelope path.** The output envelope lies at the weight between the two, bin by bin in
   decibels.
5. **The excitation choice.** Under that envelope sounds the excitation the settings name: the
   first sound's whole, the second's whole, or the two crossfaded linearly with the weight.
6. **Synthesis.** The product of the two is a magnitude, which phase gradient heap integration
   makes audible, as for every route over the analyses.

The ends render through the same steps as every point between them. Under a kept excitation the
kept sound's own end reconstructs its analysis, since an envelope times its own excitation is the
spectrum it came from, and the far end is that sound's pitch content under the other sound's
envelope. Under the crossfade both ends reconstruct their sounds. Nothing is substituted at an
end, so a slider says at 1.0 exactly what the path arrives at.

## Parameters

`EnvelopeSettings` (`samplemorph/envelope/settings.py`) holds four settings.

| Parameter | Default | What it does |
|---|---|---|
| `coefficient_count` | 40 | How many cosines draw the envelope. Fewer make it smoother, so more of a sound's fine structure counts as excitation; more let it follow individual harmonics, so less of the timbre travels. At 40 over the 1,025 bins of a 2,048-point analysis, the envelope keeps ripples slower than about 50 bins per cycle. |
| `floor_db` | 80 | How deep under the sound's loudest bin the loudness is read. A silent frame's envelope lies flat at this floor. |
| `excitation` | `first` | Whose excitation sounds under the moving envelope: `first` keeps the first sound's along the whole path, `second` the second's, and `both` crossfades the two with the weight. |
| `timeline` | `morphed` | Whose course through time the path is heard on: `morphed` runs between the two lengths, and `first` or `second` holds one sound's course, so every point lasts exactly as long as that sound. |

The three choices give three different paths:

| `excitation` | The middle sounds | The far end sounds |
|---|---|---|
| `first` | the first sound's pitch content under an envelope halfway toward the second's | the first sound's pitch content under the second sound's envelope |
| `second` | the second sound's pitch content under an envelope halfway from the first's | the second sound's pitch content under the first sound's envelope |
| `both` | both pitch contents, each at half its level, under the halfway envelope | each sound's own spectrum at its own end |

The inference process reads the route and these settings from `morph.yaml` at the repository
root, and the committed file names the envelope route with `excitation: first`. The listening
comparison renders the route beside the others with `morph compare --routes envelope --excitations
first second both`, one folder per choice.

Because the envelope is drawn over the analysis bins, and a bin is a fixed fraction of the rate a
pair is heard at, the envelope's resolution in hertz follows that rate: a pair heard at 8 kHz gets an
envelope about five times finer in hertz than one heard at 44.1 kHz.

## What the measurements showed

Four listening pairs were rendered at weights 0.25, 0.5 and 0.75 under `first` and `second`, beside
a decibel crossfade, and the notes at each midpoint were read with the same estimator the partials
route uses.

| Pair | The ends | `first` | `second` | crossfade |
|---|---|---|---|---|
| a lead against a lead a fifth apart | 524 Hz / 353 Hz | 524 Hz | 354 Hz | two notes, 1054 and 499 Hz |
| a chord against a chord | three notes / three notes | the first chord's three notes, within 1 Hz | three notes, all the second chord's | three notes from both |
| a piano chord against a piano note | four notes / one note | four notes | one note | two |
| a tone against itself an octave up | 293 Hz / 587 Hz | 293 Hz | 586 Hz | two |

Every render holds exactly one sound's pitch content; the crossfade holds both. Nothing was
estimated to get there: no partials tracked, no fundamentals found, no series to complete.

Whether the timbre travels was read from a 12-coefficient envelope of each render, coarse enough to
ignore where the harmonics stand, as the fraction of the way from the first sound's envelope to the
second's:

| Pair | `excitation` | w = 0.25 | w = 0.5 | w = 0.75 |
|---|---|---|---|---|
| piano chord against piano note | `first` | 0.27 | 0.46 | 0.62 |
| piano chord against piano note | `second` | 0.63 | 0.77 | 0.89 |
| lead against lead | `first` | 0.20 | 0.37 | 0.40 |

The timbre moves with the weight on every pair, and it moves less than the weight says, offset
toward whichever sound's excitation is kept. This is a property of sound rather than of the
implementation: where a sound's harmonics stand is itself part of its coarse spectral shape, so
holding one excitation bounds how far the timbre can travel. Pitch and timbre are far more separable
than a partial-wise morph assumed, and not fully so.

## What the route does and does not give

- **The middle is one instrument, not two.** That was the whole difficulty, and it holds by
  construction.
- **The path is asymmetric.** Under `first`, morphing A toward B and B toward A give different
  sounds: each keeps its own first sound's pitch content. A slider in the application therefore
  plays A's notes with a timbre moving toward B's, and arrives at A's notes under B's envelope; B's
  own notes are never heard on that path. The ends render by the same rule as every point between
  them, so the slider says what the path does instead of substituting the samples at its ends.
- **Pitch never glides.** A path holding one excitation keeps its pitch content from end to end,
  and `both` crossfades two pitch contents, which is the middle every crossfade has. For a chord the
  kept excitation is the only honest reading: consonance is discrete, and every continuous path
  between two chords passes through roughness that neither end has. For a single note, transposing
  the excitation continuously would be well defined, and the route does not do it yet.
- **Rhythm is the kept excitation's.** Silence in the kept sound's frames stays silent whatever the
  other sound does there; the other sound contributes its shape, not its events.
- **Percussion is a filter sweep.** With no pitch content to keep, the route plays the first sound
  through an envelope moving toward the second's. Whether that is a morph or an equalizer is a
  matter for the ear, and it has been heard on tonal material only so far.

## The held timeline, and the filter the route becomes

The time map the route reads is built at the morph weight, so the path's length runs from one
sound's to the other's along a geometric curve (`transport/time_map.py`): a one-second sample against
a two-and-a-half-second one plays for one second at weight 0 and for two and a half at weight 1.
For listening at a slider that is the honest reading. For an instrument playing a note at a time it
is unusable, because turning a knob changes how long the note lasts.

`Timeline` holds the map to one end instead. The weight-dependence of the alignment is shallower
than it looks: the correspondence between the two sounds' frames is weight-free, and the weight only
sets the output length, places the onset and reparameterizes the traversal. At weight 0 the first
sound's positions are the identity and its rates are all 1, which the transport's own tests pin, so
a map built there reads the first sound exactly as it was analyzed and the second compressed onto
its grid.

That is what turns the route into a filter. With the map held to the first sound and its excitation
kept, the magnitude at weight `w` is

    magnitude(w) = envelope_first^(1-w) · envelope_second^w · excitation_first
                 = magnitude_first · (envelope_second / envelope_first)^w

because the kept excitation *is* the first sound's magnitude divided by its own envelope. The first
sound's own spectrum appears undivided, so its measured phase can be used and the phase gradient
integration — around 85% of what a render costs — is not needed at all. Held to the second sound the
form mirrors: `magnitude_second · (envelope_first / envelope_second)^(1-w)`, on the second sound's
course and at its length.

The ratio is cheap to carry. An envelope is `exp(idct(dct(log magnitude)[:coefficient_count]))`, so
its logarithm *is* an inverse cosine transform of `coefficient_count` numbers, and the logarithm of
the ratio between two envelopes is the inverse transform of the difference of their two cepstra.
The whole path between two sounds is therefore 40 floats per frame — about 55 KB per second of audio
against 1.4 MB for the same thing bin by bin — and a weight is one number multiplying them before
they are read back.

`samplemorph.envelope.response` measures both filters of a pair, one per held end, and
`samplemorph.envelope.filtering` applies either at any weight; `samplemorph.envelope.payload` writes
them as bytes a reader of any language parses. `samplelibrary morph response` exports that file and
`GET /morph/response` serves it, which is what lets a caller ask once per pair and then move a
knob without asking again.

What it does not do: `both` has no filter form, since it crossfades two excitations and the second
sound arrives with no phase of its own. And a held path is not the morphed path — the far sound's
envelope is read along the held sound's course, so a short sound against a long one contributes a
stretched envelope. `morph compare --timelines morphed first` renders the two side by side for the
ear to settle.

## Where this stands

The route is the one the application serves. What it leaves open is the excitation itself: a way
to move it between two sounds that keeps a chord one chord at every point, which is the question the
partials route could not answer either. The next direction is a learned representation whose
straight lines move features, conditioned so that its coordinates do not collapse to a spectrum;
the timbre-transfer literature is the place to read for how such spaces are trained.
