# Terms

The morph documents use a small vocabulary precisely, and two of the words also have looser everyday
meanings in music. This page fixes what each one means here. Where the code's meaning is narrower
than the general acoustic one, both are given, because the difference matters when reading numbers.

## Words for what a sound is made of

**Partial.** One sinusoidal component of a sound: a single frequency with a single amplitude, both
free to change slowly over time. Any sound can be written as a sum of partials. The word carries no
assumption about how the partials relate to one another — a bell's partials stand at ratios no
integer explains, and they are partials all the same.

**Harmonic.** A partial whose frequency is a whole multiple of some fundamental. Harmonic `k` of a
note at `f0` stands at `k · f0`. Every harmonic is a partial; most partials in the world are not
harmonics. When a sound's partials are harmonics of one fundamental, it has a pitch.

**Fundamental, `f0`.** The frequency whose whole multiples a harmonic series stands on — usually,
but not always, the lowest partial present. A tone can sound its harmonics 2, 3, 4… with nothing at
`f0` and still be heard at `f0`; this is the *missing fundamental*, and it is why pitch is read from
the spacing of the partials rather than from the lowest one.

**Inharmonicity, `B`.** How far a real string's harmonics stand above whole multiples, because
stiffness makes higher modes travel faster: harmonic `k` sounds at `k · f0 · √(1 + B k²)` rather
than at `k · f0`. A piano's `B` is around 1e-4; an ideal string's is 0.

**Residual.** Everything in the spectrum that the partials do not explain: broadband noise, the
click of an attack, and clusters too dense to resolve into separate partials. A sound is modeled
here as partials *plus* a residual, and the two are rendered by different machinery.

## Words for what the analysis produces

These are the code's own objects, in the order they are built.

**Peak** (`partials/peaks.py`). A local maximum in the magnitude spectrum of **one frame** that
passes the tests for being a sinusoid rather than a ripple of noise. A peak is a measurement at one
instant and has no history.

**Track** (`PartialTracks`, `partials/tracks.py`). Peaks in consecutive frames joined into one
continuous line, held to a minimum length of 0.1 s. **This is what the code means by "partial".**
A track is stored as two arrays over the analysis frames — a frequency and an amplitude — with
amplitude 0 on frames where it is silent. So when a table says a sound has "35 partials", it means
35 tracks survived that 0.1 s rule, not that the spectrum contains 35 sinusoids.

**Note** (`Note`, `partials/notes.py`). A fundamental over time plus an inharmonicity, estimated
from the tracks, together with which track sounds each of its harmonics. A note is an *inference*,
not a measurement: a sound may hold none (a snare), one (a bass), or several (a chord).

**Channel** (`Channels`, `partials/channels.py`). What the oscillator bank actually plays. A channel
is either harmonic `k` of a note — standing at `k · f0(t) · √(1 + B k²)`, and silent on frames where
no track sounds it — or a **free partial**, a track that belongs to no note and keeps its own
measured frequency. Channels, not tracks, are what a morph pairs and moves.

The distinction earns its keep in one place: a note's harmonics all follow *one* fundamental
estimate, so a vibrato the whole note shares survives while the measurement jitter of each
individual track cancels. That is what removed the transport's warble.

**Line** (`Channels.lines`). The group a channel belongs to: the note it is a harmonic of, or one of
its own if it stands free. Lines are what let the correspondence say "these channels are the same
thing and must travel together".

**Fate** (`Channels.fate`, `partials/fate.py`). Which set of channels a channel rises and falls
with, read from the shape its loudness draws over the whole sound. Two partials of one struck string
swell and decay together; two sounds struck apart do not. This is the grouping cue from auditory
scene analysis, and it asks nothing about whole multiples, so it holds for a bell as well as a
string.

**Object**, or **unit** (`Channels.units`). What travels as one thing in a morph: a whole note, or
the partials standing free of every note that share a fate. Harmonicity binds a series and separates
two notes struck together; fate binds what no series explains. Each does the job the other cannot.

**Place** (`PartialPlaces`, `partials/places.py`). A channel reduced to the three numbers a pairing
reads it by — the pitch it holds, the share of the sound's energy it carries, and the stretch of time
it is heard over. It is a summary of a channel, not a separate object.

## Words for what a morph does

**Weight.** Where a rendered point sits between the two sounds: 0 is the first sound exactly, 1 is
the second exactly.

**Move** (or *shift*). An interval, in cents, that a channel travels between the two sounds. A whole
line usually travels by one move; a chord travels by one move per voice.

**Pairing** (`ChannelPairing`). Which channel of the first sound travels to which channel of the
second, which channels of each travel alone, and the move each line makes. Read **once** for a pair
of sounds and held at every weight — that fixedness is what keeps a partial on one path from end to
end. How it is decided is [`22-correspondence.md`](22-correspondence.md).

**Fade.** What a channel does when it meets nothing in the other sound: it holds its own pitch and
its level falls to silence.

**Profile** (`MorphProfile`). Frozen data naming what the middle of two sounds should be: who meets
whom, how a matched pair travels in pitch, when an unmatched channel fades, and when each aspect
moves. A **preset** is a named profile. See [`21-partials.md`](21-partials.md).

**Route.** One complete way from two sounds to a point between them — `latent`, `transport`,
`blend`, `partials`. Routes are interchangeable behind one interface so a listening comparison can
render them side by side.

**Degeneration.** The property that the partials route, given two sounds with no tracked partials,
renders bit for bit what the transport route renders. It is what lets the route be adopted for tonal
material without changing what percussion already sounds like.

## Words this vocabulary avoids

| Word | Why |
|---|---|
| **Overtone** | Ambiguous by one: the first overtone is the second harmonic. Say "harmonic `k`". |
| **Voice** | Reserved for its musical sense — one note of a chord moving to another. The per-channel summary a pairing reads is a **place**, never a voice. |
| **Frequency bin** | A property of one spectrum, not of a sound. Partials sit between bins; the analysis reads where, to a fraction of one. |

## One sound, in these terms

A piano note sampled for 2 seconds:

- the spectrum holds a few dozen **peaks** per frame;
- joined over time they become about 20 **tracks**, each a partial that lasts;
- the tracks fit one **note** — a fundamental near 220 Hz with an inharmonicity near 2e-4 — whose
  harmonics explain most of them;
- that note becomes about 20 harmonic **channels**, all following one fundamental, on one **line**;
- the hammer's knock and the soundboard's noise stay in the **residual**;
- morphing it into another piano note, the whole line takes one **move**, every channel follows it,
  and the residual travels by transport underneath.
