# Partials: a morph whose middle is a chord you choose

The spectral transport of [`20-audio-transport.md`](20-audio-transport.md) moves features, and on
percussion it does so convincingly. On tonal material it fails: the midpoint between two chords
carries a heavy vibrato that makes it unusable, while the same route on a snare or a hi-hat is fine.

This document explains where that vibrato comes from, describes the sinusoidal-plus-residual model
built to remove it — a sound read as notes and their harmonics over the noise they stand in — and
sets out the profile that names what the middle of two sounds should be, since once partials travel
along paths, the paths become a choice rather than a consequence.

## Why the transport warbles on tonal sounds

The transport recomputes everything per output frame: the groups a spectrum is cut into, their
energy centers, and the monotone plan that pairs them. On a steady chord the centers wander 10–16
cents from frame to frame, the pairing shifts with them, and balanced transport splits about every
group into two pieces (1.95 per group on the listening set) that land a few cents apart and beat.

Measured on the listening set (`runs/transport-2026-09-15/`), the midpoint against the two ends:

| Reading | Transport midpoint | Its own ends |
|---|---|---|
| Partial wobble, cents per 3 ms heard (chord 15) | 2.05 | 0.68 / 1.07 |
| Partial wobble (lead 09) | 5.06 | 0.70 / 0.35 |
| Roughness excess | +0.09 to +0.12 | |
| Harmonicity, the share of partial energy standing on notes | 0.00–0.64 | 0.78–0.99 |

Harmonicity says it plainly: the midpoint of two chords holds no note at all. The partials are
still there, and no harmonic series runs through them any more.

## The model

`samplemorph.partials` reads a sound as partials over a residual, on the same hop as the transport
analysis (128 samples), so every frame of one stands beside a frame of the other.

- **Peaks.** A Gaussian window about 93 ms long as heard, rounded to a power of two, so every rate
  resolves partials alike. The log-parabola vertex over three bins is exact for a Gaussian lobe. A
  peak reads as a sinusoid when it rises 12 dB over the median of the 16 bins on either side and its
  lobe curves within [0.1, 1.33] of a stationary sinusoid's; a gliding partial spreads into a wider
  lobe, lower by the fourth root of its curvature ratio, and is read back up by that root.
- **Tracks.** Mutual-nearest continuation within 12000 cents per heard second, gaps of up to two
  frames bridged, and a track lasts at least 100 ms. That length is what separates a partial from a
  noise peak: a noise peak holds for about one window, and on the listening set the rule leaves
  80–100 % of a tonal sample's energy in tracks and 0–30 % of a snare's or a hi-hat's.
- **Amplitude.** Each partial's amplitude is the quieter of the long window's reading and the
  transport analysis's own, which holds a partial to the strike it belongs to: a struck tone's
  partial rises 3 frames before its onset rather than 7.
- **Notes.** Every partial taken as a harmonic proposes a fundamental, and a proposal is worth the
  loudness of the partials it sounds, each weighed by `(f0 + 52) / (f + 320)` (Klapuri, 2006), which
  is what keeps a major triad from reading as the note two octaves under it. A proposal sounds
  through at least 3 harmonics and through 70 % of those between its lowest and its highest; where
  the note under it sounds the partials in between as one unbroken series, that deeper note stands
  instead, which is how a tone whose fundamental is quiet keeps its own pitch. The note found then
  takes every partial standing on its series, as high as the sound's partials reach and including a
  harmonic sounded by two tracks at once — the proposal is made over 20 harmonics, which is enough to
  find a note, while the series itself carries on. Taking all of it is what keeps the partials above
  the twentieth from reading as a second note a whole multiple higher: two such notes travel by
  different intervals, and one measured partial then arrives at the midpoint as two. A partial two
  notes share is counted in both, and the search runs again on what is left. A stiff string's stretch is fitted per note, and a piano-like tone reads
  its own inharmonicity within 1e-4.
- **Channels.** Every harmonic between the lowest and the highest a note sounds becomes a line of
  its own, standing at `k · f0(t) · stretch(k)` and silent where no partial sounds it. A note's
  fundamental is read through all its harmonics at once, so measurement jitter cancels while a
  vibrato the whole note shares stays. A partial two notes share is split by what each note's other
  harmonics predict it to hold, and the halves sum to the partial as measured. Partials no note
  sounds stay lines of their own.
- **Residual.** What each partial's lobe explains, with 3 dB of headroom, comes off the analysis,
  down to a floor read as the least energy within 8 bins. A sound with no partial to its name keeps
  its energy bin for bin, which is what makes the route degenerate to the transport on noise.

A point between two sounds is then: the time map on the two whole analyses, the channels read along
it, the profile's paths applied, a phase-continuous oscillator bank, the two residuals through
`transport_along` on the same map and the phase integration, and the two sounded together.

## The profile: what the middle is

`MorphProfile` is frozen data with one weight going in. It makes four separable choices.

**Correspondence — who meets whom.** Read once per pair of sounds, never per frame and never per
weight, which is what removes the wobble. Every channel of one sound may travel to any one channel
of the other or fade where it stands, each at a price, and the pairing taken is the cheapest over
both sounds: `travel_cents` says how far a partial will go before fading comes cheaper,
`drift_cents` how far it may travel against the moves the rest of the sound makes, and `fade_price`
what standing still is worth. [`22-correspondence.md`](22-correspondence.md) walks through it.

**Pitch path.** `glide` moves evenly in pitch; `stepped` moves in whole semitones, a partial that
has travelled half a step standing at the next one; `switch` arrives at the halfway mark.

**Fade law.** A partial meeting nothing fades by `level_path`, `early` (gone by the middle) or
`late` (held to the middle).

**Aspect curves.** Pitch, timbre, level, time and residual each read the one weight through a curve
of its own: `start`, `end` and `linear` or `eased`. Both ends stay exact.

### The presets, on C4-E4-G4 → C4-F4-A4

| Preset | Midpoint |
|---|---|
| `glide` (default) | C4, 339 Hz (E4 + 48 cents), 415 Hz (G♯4) |
| `stepped` | C4, F4, G♯4: every point is a chord a keyboard holds |
| `eased` | The glide with pitch moving over 0.25–0.75, in tune longer near both ends |
| `switch` | The first chord until the middle, the second after it |
| `pivot` | C4 holds at its own level; E, G, F and A stand at their own pitches, 3 dB down |
| `slide` | Partials slide in frequency order |
| `crossfade` | Both chords at once, each 3 dB down |

`morph compare --routes partials --profiles glide stepped … ` renders one folder per preset and
records every profile's JSON in the manifest.

## The contracts

`tests/samplemorph/partials/`, on synthetic sounds:

| Contract | Reading |
|---|---|
| A noise-hit pair renders bit for bit as the transport route | `np.array_equal` |
| A tone plus noise 20 dB under it: the residual near the harmonics | at the noise floor |
| Each end's harmonics | within 0.5 dB of the sound's own |
| 220 → 330 Hz tones of different brightness, midpoint energy on the 269 Hz series | ≥ 95 % |
| Midpoint of two chords: wobble, roughness excess, harmonicity | ≤ 3 cents, ≤ 0.02, ≥ 0.9 |
| C-E-G → C-F-A at every weight | the three voices within 5 cents of their own paths |
| A chord read as notes | 3 notes within 5 cents |
| A tone whose fundamental is missing | its own pitch |
| A stiff string (B = 4e-4, 20 harmonics) | one note, ≥ 90 % of its energy |
| A struck bar | no note, every partial free |
| A partial gliding past what the rate carries | fades out, nothing folds back |
| A 3 s midpoint | renders in 1.4 s |

On the real listening pairs, the glide profile against the transport at the midpoint:

| Pair | Wobble excess, cents | Roughness excess | Harmonicity |
|---|---|---|---|
| 15 chord | +1.17 → −0.16 | +0.094 → +0.026 | 0.00 → 1.00 |
| 22 lead to chord | +1.57 → +0.18 | +0.093 → +0.033 | 0.64 → 0.94 |
| 09 lead | +4.54 → −0.21 | +0.115 → +0.039 | 0.00 → 0.98 |

## The gate

- **Pass:** on tonal pairs a partials preset is preferred over the transport on at least four pairs
  with at most one bad example, and percussion is no worse. By degeneration it is the transport
  there, so what the ear judges on percussion is what tracking leaves as partials.
- **Then:** the service renders `partials` on the chosen preset, and the transport plan's service
  phase is retargeted to it.
- **An artifact heard twice** is answered by a named variant rendered on the failing pairs:
  envelope timbre, lobes painted into the magnitude, oscillators starting from measured phases,
  pairing per epoch for sounds holding several events.
