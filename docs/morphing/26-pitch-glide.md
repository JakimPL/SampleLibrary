# The pitch glide: the envelope route reading a pitch and moving it

[`23-envelope.md`](23-envelope.md) ends with a route that keeps one sound's excitation whole under a
moving envelope, so a morph holds exactly one pitch content and never plays two notes at once. That
is what the application serves. It also never glides: at every point the kept harmonics stand where
they stood, and the pitch arrives all at once at the far end, where the other sound's envelope takes
over. [`24-learned-features.md`](24-learned-features.md) calls this Step 0 — a glide driven by a
classical pitch reader, which needs no training and says how much of the gap a learned coordinate
would have to close.

This document is Step 0, built and heard, and the readings that come with it.

## The reader before the route

Two classical readers are built first (`samplemorph.coordinates.readers`), both returning a pitch in
semitones from 440 Hz in the nominal frame and a reliability in ``[0, 1]``:

- **`subharmonic`** — Hermes's subharmonic summation (1988) over the constant-Q frames a pitch head
  reads (36 bins per octave from 32.70 Hz, `filter_scale` 0.5, 16 frames kept, floors at 60 dB under
  each frame's peak and 70 dB under the sample's). The best bin is refined by a parabola through the
  logarithms of three scores. Reliability is how far the peak stands over the median score within an
  octave of it, the peak's own semitone set aside.
- **`pyin`** — probabilistic YIN (Mauch and Dixon, 2014) over the waveform, the median of its voiced
  frames, with the voiced share times the mean voicing probability as reliability.

`morph read-pitch` (`samplemorph.measurement.pitch`) reads both against known answers: true
retunings of held-out samples at 16 intervals to ±17 semitones, 11 synthetic tone families rendered
clean and as 8-bit samples at 8,363 Hz, intervals between tones of different timbres, changes that
keep the pitch (time stretch, level, 8-bit rounding, the envelope route's own middle), and noise
bursts that have no pitch at all. On 20 held-out samples:

| Reading | `subharmonic` | `pyin` |
|---|---|---|
| Retunings within 0.5 st, top reliability tercile | 99% | 100% |
| Retunings within 0.5 st, bottom tercile | 41% | none read |
| Synthetic families within 0.5 st | 100% | 80% |
| Tones against noise bursts, area under the curve | 1.00 | 0.99 |

The families were expected to expose Hermes's octave errors. They exposed pYIN's: with the resonance
on the second harmonic it reads the octave above every time, and on the third harmonic a twelfth
above half the time. Hermes over these frames reads every family right, including a missing
fundamental and a stiff string. Its errors are elsewhere — on drums, where its reliability is low,
and that is what the reliability is for. Above 0.5 it follows 97% of true retunings within half a
semitone, and every drum-like sample of the draw read below 0.4; 0.5 is the threshold the route
trusts.

## The glide

`samplemorph.envelope.glide` carries the kept excitation. At weight `w` between two ends whose
pitches lie `d` semitones apart, the first end's excitation is carried by `2^(w·d/12)` and the
second's by `2^(-(1-w)·d/12)`, so both arrive at the pitch `w` of the way between them:

- each frame of the excitation is cut into grains at its own valleys and moved by `place_groups`,
  the transport's own placement, which carries a lobe rigidly with its width and its energy. A
  harmonic therefore arrives as the lobe it was, which is what phase gradient integration reads a
  partial from. Interpolating the excitation along frequency instead would widen every lobe as it
  rose.
- what is carried past the top of the spectrum leaves it, and what is carried down leaves the top
  empty, exactly as a retuning does.
- the envelope is smoothed for the glide: the `q`-th cepstral coefficient draws a ripple `2N/q` bins
  long, and a comb whose harmonics stand `p` bins apart is a ripple of that length, so the route
  keeps `N/p` coefficients at most, `p` taken from the higher of the two pitches. Without this the
  envelope of a note above about 1.1 kHz in the nominal frame holds its own harmonic comb, and the
  comb crossfades under the gliding harmonics as a ghost of the switch.

A route glides only where both ends read at or above the reader's trusted reliability; any other
pair renders exactly as the route without the glide, which is what drums and noise do.
`EnvelopeSettings` is untouched, so every response and every ETag built before this stays valid.

## What the listening set showed

The 26-pair listening set — the one `morph draw-pairs` wrote for note 20 and every comparison has
used since — rendered through four routes: the envelope route keeping the first sound's excitation
and crossfading both, each with and without the subharmonic glide.
16 pairs glide; the rest read no trusted pitch at one end. Pitch paths are read by pYIN, which never
drives the glide. Jump share is the largest step over the whole span — 0.125 is an even glide over
the eight steps, 1.0 a switch:

| Pair | first | first + glide | both | both + glide |
|---|---|---|---|---|
| 08 bass | 1.00 | **0.14** | – | **0.15** |
| 09 lead | held | **0.13** | 0.95 | **0.13** |
| 11 pad | 1.00 | **0.13** | 0.97 | 0.43 |
| 12 pad, +24 st | 1.00 | 0.42 | 0.50 | **0.13** |
| 13 piano, −13 st | 0.50 | 0.64 | 0.98 | **0.13** |
| 20 bass→lead, +22 st | 1.00 | **0.13** | 0.64 | 0.65 |

Where the path reads clean the glide moves in even steps and deviates from the straight line by
about 0.1 semitone. Where it does not, pYIN reads an octave jump partway along, on the wide
intervals and on the pairs whose ends are chords rather than notes.

## Verdict

Heard by the user (2026-09-19): **the crossfaded excitations gliding together** —
`envelope-both-glide-subharmonic` — is what a morph between two notes should sound like. It is the
one route that both moves the pitch and carries both timbres, and it removes the two-notes-at-once
defect that made `both` unusable before: the two excitations now sound at one pitch, so they add up
as one note instead of a chord.

The routes stand side by side rather than replacing each other. `glide: subharmonic` turns any
envelope route into its gliding form, and `morph compare --glides` renders both for listening.

On the user's decision (2026-09-21) the gliding crossfade is what the application serves: the
committed selection now names `excitation: both` with `glide: subharmonic`. The morph filter a VST
reads is refused under a glide, by the command and by the service alike — that filter is the
identity `magnitude(w) = first · (envelope_2 / envelope_1)^w`, which holds while the harmonics stay
put and fails once they move — so the filter keeps a committed selection of its own, naming the
envelope route with no glide, which `morph response --selection` reads it under. The renderer glides
and the filter holds still, each under its own file.

## Where this stands

The glide is now a control, not an endpoint. The pitch it follows comes from a classical reader, and
[`24-learned-features.md`](24-learned-features.md) Step 2 asks for a learned one: a
transposition-equivariant head trained on the library's own frames, which has to read one pitch
across timbres at least as well as refined Hermes does before it drives anything. Note 27 will
report it, against this route as its control.
