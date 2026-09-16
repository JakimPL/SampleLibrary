# How a partial finds its partner

A morph is only a morph if things *move*. This document explains, in plain terms, how the partials
route decides which partial of the first sound travels to which partial of the second — the one
decision that separates a glide from a crossfade.

## What went wrong first

The first version had four separate rules, picked by what the analysis found:

- if both sounds had notes, notes met note to note and harmonic `k` met harmonic `k`;
- whatever was left met by pitch, but only within 100 cents;
- if no notes were found, *everything* fell to that 100-cent rule.

The last line is the bug. Two bass samples a minor third apart are 293 cents apart, so nothing could
meet, so nothing moved, so the morph was a crossfade — exactly what it was built to avoid. On the
26 listening pairs this happened to 9 of them, and on those nine every preset rendered the same file.

The cause was a cap. A cap says "too far apart to be the same thing", which is right for a duplicate
detector and backwards for a morph: a morph *wants* to travel far.

## The idea

Replace all four rules with one, and replace the cap with a price.

> Every partial may travel to any one partial of the other sound, or fade where it stands.
> Travelling has a price that grows with how strange the journey is. Fading has a fixed price.
> The pairing chosen is the cheapest for the two sounds as a whole.

Nothing is forbidden, so distance never blocks a meeting — it only makes it expensive. And because
everything is priced in one currency, the presets become dials on that currency rather than
different algorithms.

## The algorithm, step by step

Take the worked example throughout: **C-E-G → C-F-A**, each note sounding ten harmonics.

### 1. Every channel becomes a voice

The analysis has already broken each sound into *channels*: each harmonic of each detected note, and
each partial that belongs to no note. Each channel is reduced to three numbers:

| | meaning |
|---|---|
| **pitch** | where it sits, in cents, averaged over its life and weighted by how loud it is |
| **share** | how much of the sound's energy it carries, so the whole sound sums to 1 |
| **life** | when it is heard, as a span from 0 to 1 across the stretch the sound sounds through |

The life is measured against each sound's *own* span, so a 0.2-second hit and a 3-second pad are
read on one clock.

### 2. A first pairing, before any move is known

Build a table of what every possible pair would cost, then solve it. This is the **assignment
problem**, and `scipy.optimize.linear_sum_assignment` solves it exactly — not greedily, not pair by
pair, but the whole table at once, so a cheap pair can be passed over when it would force an
expensive one elsewhere.

Fading is offered as a choice inside the same table: each partial gets its own "fade" column priced
at `fade_price`. A partial takes it when no partner is worth the price.

This first pass charges for distance, loudness and time, and stays silent about the fourth term —
there are no moves to agree with yet. On the example it pairs C with C, E with F and G with A, and
their harmonics likewise, simply because those are the shortest journeys.

### 3. Read back the moves

Now ask the pairing what it just did. Every pair votes for the interval it travelled, weighted by
what the two partials carry. Blur the votes a little (20 cents) and look for peaks.

On the example the votes pile up at three places:

```
−197.5 cents     −97.5 cents     −2.5 cents
   (G→A)            (E→F)          (C→C)
```

These are the **moves the two sounds agree on**. Nobody told the algorithm there were three notes;
it found three intervals because thirty partials voted for three numbers.

At the same time, each *line* — a note's harmonics, or a lone partial — is asked what move its own
pairs stand on. A line with at least two pairs holds the interval that half of what it carries
travels by. So "the G line moves by −200 cents" becomes a fact about that line.

### 4. Pair again, now knowing the moves

Redo the assignment with one term added: a partial is charged for travelling *against* the move it
is held to. A channel on a line that has a move is held to that line's move; a channel standing on
its own is held to the nearest of the moves the two sounds agree on.

This is what settles the ambiguities. In the example, the first chord has two channels within two
cents of 785 Hz — C's third harmonic and G's second — while the second chord has only one partial
there. Pitch alone cannot say which is which, and the cheapest answer by distance is the wrong one:
let the *quiet* channel make the long journey. Knowing that the G line moves by −200 settles it: G's
second harmonic travels to 880 Hz, C's third stays at 785 Hz.

### 5. Settle

Steps 3 and 4 run twice: read the moves, pair again, read the moves the new pairing makes, pair
once more. Two rounds is enough because the first pass is already close — shortest journeys are
usually the right journeys, and the later passes only fix the crossings.

## The price list

Four things make a journey expensive. Each is scaled so that **1 is worth one whole fade**, which
makes them directly comparable.

| Term | Charged for | Worth a whole fade when |
|---|---|---|
| **travel** | the distance covered | the distance reaches `travel_cents` |
| **drift** | travelling against the move it is held to | the disagreement reaches `drift_cents` |
| **loudness** | standing at a different loudness | one of the two is silent and `level_weight` is 1 |
| **lifetime** | being heard at a different time | the lives never overlap and `lifetime_weight` is 1 |

Travel and drift are raised to `exponent`, which defaults to 2. Above the first power, several short
journeys cost less than one long one, so a chord's movement spreads across its voices rather than
loading one of them.

A pair is then charged `(share_first + share_second) / 2` times that total, and a fade costs a
partial `share / 2` times `fade_price`. Two partials of equal weight therefore travel exactly when
their total price comes to less than `fade_price` — which gives the one number worth remembering:

> **A partial that agrees with the move its sound is making will travel up to `travel_cents` before
> fading becomes cheaper.** At the default that is two octaves.

### Why loudness sits at rest

`level_weight` defaults to 0, which is worth explaining, because matching partners by loudness is
a natural thing to want. It actively harms a morph: a partial that is loud in one sound and quiet
in the other is *exactly* what a morph should carry, and charging for that difference makes quiet
upper harmonics marry the wrong series. Measured on the worked example, a loudness weight of 0.05
was already enough to send C's fifth harmonic to the F series. The dial remains for experiments.

## The parameters

| Name | Default | What raising it does |
|---|---|---|
| `travel_cents` | 2400 | lets partials travel further before fading |
| `drift_cents` | 300 | tolerates journeys that disagree with the rest of the sound |
| `level_weight` | 0 | prefers partners of similar loudness |
| `lifetime_weight` | 0.1 | prefers partners heard at the same time |
| `exponent` | 2 | spreads movement across voices instead of loading one |
| `fade_price` | 1 | sends more partials travelling instead of fading |
| `largest_shift_count` | 4 | allows more distinct moves at once — one per voice |
| `shift_spread_cents` | 20 | groups votes more loosely into one move |

Two resolutions are fixed in the code rather than offered as dials: the votes are counted over
±4800 cents in 5-cent steps, and a move must stand at a tenth of the tallest to count as one.

## The presets are dials, not algorithms

| Preset | How it is set | What you hear |
|---|---|---|
| `glide` | the defaults | every partial travels to its partner |
| `stepped` | `glide` plus a stepped pitch path | the same journeys, taken in semitones |
| `eased` | `glide` plus an eased pitch curve | in tune longer near both ends |
| `switch` | `glide` plus a switching pitch path | the first chord until halfway |
| `pivot` | `travel_cents` 50, no moves read | shared partials hold, everything else fades |
| `slide` | `fade_price` 1000, no moves read | nothing fades; partials slide in frequency order |
| `crossfade` | `fade_price` 0 | fading is free, so nothing meets: the control |

Two of these are worth a note. **`slide`** reduces to the old ordered pairing exactly: with only a
distance term raised to an even power, the cheapest assignment over points on a line is always the
one that keeps their order, so monotone sliding falls out rather than being coded. And **`crossfade`**
is the honest control — it is the same oscillators and the same residual as every other preset, with
the meeting priced out of existence.

## What it does on the listening set

Pairs matched, before and after, on the 26 pairs:

| Pair | before | after |
|---|---|---|
| 01 bass drum | 0 | 1 |
| 04 snare | 0 | 1 |
| 07 bass (a minor third apart) | 0 | 3 |
| 09 lead | 21 | 26 |
| 15 chord | 96 | 101 |
| 22 lead → chord | 31 | 61 |
| 24 retuned percussive | 0 | 4 |
| 25 short hit → long sustain | 0 | 1 |

Reading the rendered midpoints back as partials shows the difference plainly:

| Pair | first | second | `glide` midpoint | `crossfade` midpoint |
|---|---|---|---|---|
| 01 bass drum | 96.6 Hz | 39.5 Hz | **66.0 Hz** | 38.8 Hz |
| 09 lead | 524.2 Hz | 353.9 Hz | **430.7 Hz** | 353.8 and 524.3 Hz |

430.7 Hz is exactly the geometric mean of 524.2 and 353.9: one partial, halfway along. The crossfade
holds both ends at once, which is the thing the route exists to avoid. The kick's body tone now
sweeps rather than dissolving.

Only three pairs still meet nothing — 03, 06 and 18 — and in each of those one of the two sounds
holds no tracked partial at all, so there is nothing to pair. That is the degeneration contract, not
a threshold.

## Where it can still be wrong

- **Crossings between series stay hard.** The line term fixes them when the analysis grouped the
  channels into notes. Where it did not, two partials at the same frequency are genuinely
  indistinguishable by anything the correspondence can see.
- **Quiet upper harmonics wander.** They carry so little weight that many arrangements cost nearly
  the same, and a few of them land on the wrong series. They are inaudible on their own, but enough
  of them can pull an estimated note a few cents sharp.
- **The first pass can lock in.** Settling improves the pairing, it does not search globally. A pair
  of sounds whose shortest journeys are the wrong journeys will keep them.
- **Hi-hats read as chords.** Nothing here causes that, but the line term will faithfully bind
  channels into whatever lines the note estimator invented.
