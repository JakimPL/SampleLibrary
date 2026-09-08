# The corpus, measured

Every figure here was measured against the real library on 2026-09-08, on the machine that holds it
(`module_source_directory = M:/Muzyka/Moduły`, `library_root = P:/Sample/Tracker`). The queries and
probes are given so each number can be re-derived on a rebuilt catalog and compared.

The corpus you rebuild will differ slightly: extraction skips samples under the 512-frame floor and
a handful of files fail to parse, so treat these as the shape to expect rather than targets to hit.

## Scale

| Quantity | Value |
|---|---|
| Samples (distinct content hashes) | 127,492 |
| Modules ingested | 8,451 |
| Occurrences (`sample_properties` rows) | 156,260 |
| Module files walked | 8,701, of which 8,494 hold distinct contents |
| Note events | 29,382,000 |
| Hand annotations | 0 |
| Sample relations (equivalence edges) | 0 |

207 module files are byte-identical duplicates of another file, each duplicated exactly twice. The
catalog holds one module per content hash, so 8,451 modules ingest and roughly 43 files fail to
parse. Any pass that walks files and looks modules up by hash has to remember what it handled
*within the run*, because the second copy of a duplicated file looks unhandled against a set read
once at the start.

Tracker mix: mod 3,825 · xm 3,283 · it 1,066 · s3m 277.

```sql
SELECT count(*) FROM sample;
SELECT count(*) FROM module;
SELECT count(*) FROM sample_properties;
SELECT count(*) FROM note_event;
```

## Shape of the audio

| Property | Distribution |
|---|---|
| Channels | mono 126,626 (99.3%) · stereo 866 (0.7%) |
| Bit depth | 8-bit 104,702 (82.1%) · 16-bit 22,790 (17.9%) |
| Frames p10 / p25 / p50 / p75 / p90 / p99 / max | 2,210 · 4,366 · 10,074 · 26,330 · 55,000 · 181,835 · 6,240,429 |
| Total frames | 2,927,259,940 |

The corpus is overwhelmingly mono and 8-bit, and the length spread is enormous — the longest sample
is 2,800 times the shortest decile. A fixed-size analysis window is therefore a real design
constraint, not a convenience.

```sql
SELECT channels, count(*) FROM sample GROUP BY 1 ORDER BY 1;
SELECT depth, count(*) FROM sample GROUP BY 1 ORDER BY 1;
SELECT percentile_disc(0.50) WITHIN GROUP (ORDER BY frames), max(frames), sum(frames::bigint) FROM sample;
```

## Playback rate and real duration

The stored WAV header always says 44,100 Hz. That number is fiction — see
[`03-architecture.md`](03-architecture.md) for the full warning. The real reference rate for tracker
C-5 lives in `sample_properties.rate`, one row per occurrence.

| Quantity | Distribution |
|---|---|
| Rate p05 / p25 / p50 / p75 / p95 | 8,305 · 8,363 · 11,163 · 22,056 · 73,987 |
| Duration at its own rate, p25 / p50 / p75 / p95 | 0.31 s · **0.70 s** · 1.65 s · 5.09 s |

Most common rates: 8,363 Hz (58,598 occurrences — the classic Amiga C-5 rate) · 16,726 (18,037) ·
44,100 (5,404) · 88,185 (4,327) · 44,092 (2,773) · 22,050 (2,170) · 8,482 (1,967) · 8,422 (1,918).

At their own rates these are short one-shots: the median sounds for seven tenths of a second.

```sql
SELECT percentile_disc(0.50) WITHIN GROUP (ORDER BY rate) FROM sample_properties;
SELECT percentile_disc(0.50) WITHIN GROUP (ORDER BY s.frames::float / p.rate)
FROM sample_properties p JOIN sample s ON s.hash = p.sample_hash WHERE p.rate > 0;
```

## How samples get retuned

One content hash can appear at several declared rates, because a tracker instrument routinely reads
the same waveform at whatever rate a slot asks for. Measured across the catalog:

| Distinct declared rates per hash | Hashes |
|---|---|
| 1 | 120,520 (94.5%) |
| 2 | 5,515 |
| 3 | 959 |
| 4 | 280 |
| 5 | 98 |
| 6 | 64 |
| 7 | 22 |
| 8 | 12 |
| 9 or more | 22 |

**6,972 hashes (5.5%) carry more than one declared rate.** Where they do, the spread between the
highest and lowest rate is:

| | p50 | p90 | p99 | max |
|---|---|---|---|---|
| ratio | 2.0× | 2.67× | 7.90× | 64.0× |
| semitones | 12.0 | 17.0 | 35.8 | 72.0 |

Two consequences worth carrying forward. First, a sample's "true" rate is a property of a use, not
of the content — the reasoning this leads to is in
[`02-representation.md`](02-representation.md). Second, the corpus states its own realistic
transposition range: **an octave at the median, seventeen semitones at p90**, which is the range to
draw augmentation and transposition-retrieval trials from.

```sql
SELECT rates, count(*) FROM (
  SELECT sample_hash, count(DISTINCT rate) AS rates FROM sample_properties GROUP BY 1
) t GROUP BY 1 ORDER BY 1;
```

## Loops

| `loop_mode` | Occurrences |
|---|---|
| (none) | 100,110 |
| forward | 41,282 |
| ping_pong | 14,868 |

**36% of occurrences loop.** Those samples are meant to be held indefinitely, so their stored
duration understates how long the sound is heard for. A representation that treats duration as a
property of the content will be wrong about a third of the corpus.

## Names and label coverage

| Quantity | Value |
|---|---|
| Samples named by at least one occurrence | 64,690 (50.7%) |
| Samples named at all, counting instrument names | 79,391 (62.3%) |
| Distinct occurrence names | 46,733 |
| Names carried by more than one content hash | 5,167 |

`classify_sample_category` reads every name a sample goes by — each occurrence's own name plus the
name of every instrument slot reaching it — and matches an ordered keyword table. Its reach over the
whole catalog:

| Category | Samples | Share |
|---|---|---|
| **uncategorized** | **114,133** | **89.5%** |
| bass | 2,398 | 1.9% |
| hi_hat | 2,138 | 1.7% |
| percussion | 1,467 | 1.2% |
| snare | 1,457 | 1.1% |
| kick | 1,315 | 1.0% |
| lead | 1,122 | 0.9% |
| cymbal | 962 | 0.8% |
| vocal | 704 | 0.6% |
| fx | 601 | 0.5% |
| pad | 400 | 0.3% |
| loop | 397 | 0.3% |
| clap | 293 | 0.2% |
| pluck | 105 | 0.1% |

**The keyword classifier reaches 10.5% of the catalog.** This is the single most consequential
number here. Three things follow from it:

- The cloud's category coloring colors one point in ten and grays out the rest.
- Any "category coherence" figure measured against these labels was measured on a tenth of the
  corpus, and on a biased tenth: the samples that carry recognizable names are the ones from
  well-organized modules. Earlier such figures are reported in
  [`08-prior-research.md`](08-prior-research.md) with exactly this caveat.
- Those 13,359 labels are nevertheless the largest supervised signal available today, since there
  are zero hand annotations. [`05-evaluation.md`](05-evaluation.md) uses them as a held-out
  evaluation set, and [`02-representation.md`](02-representation.md) uses them as auxiliary
  supervision.

## What note events say about a sample

`note_event` holds one row per grid cell where a key was pressed: 29,382,000 rows over 8,451
modules, 94.8% resolving to a sounded note, 81.1% reaching a cataloged occurrence, 5.0% naming no
instrument, and 1.0% sounding a different note than the key pressed. Reaching a sample hash means
joining through `(module_id, instrument_index, sample_slot)`.

A probe over 300 modules reached 5,303 distinct sample hashes and found:

| Quantity | Value |
|---|---|
| Played at exactly one pitch | 2,160 (41%) |
| Distinct sounded pitches p50 / p90 | 2 / 15 |
| Pitch span in semitones p50 / p90 | 3 / 27 |

Two fifths of the samples a composer touched were struck at a single pitch, and the melodic tail
spans more than two octaves. That separates percussive material from tonal material with nobody
listening to anything, which is why [`05-evaluation.md`](05-evaluation.md) treats it as free weak
supervision. Whole-catalog coverage was left unmeasured; the probe took 10 seconds, so measuring it
properly is cheap.

```sql
WITH m AS (SELECT id FROM module ORDER BY id LIMIT 300),
     e AS (SELECT n.module_id, n.instrument_index, n.sample_slot, n.sounded_note
           FROM note_event n JOIN m ON m.id = n.module_id WHERE n.sounded_note IS NOT NULL),
     j AS (SELECT p.sample_hash, e.sounded_note FROM e
           JOIN sample_properties p ON p.module_id = e.module_id
            AND p.instrument_index = e.instrument_index AND p.sample_slot = e.sample_slot)
SELECT count(*), count(*) FILTER (WHERE pitches = 1),
       percentile_disc(0.5) WITHIN GROUP (ORDER BY pitches)
FROM (SELECT sample_hash, count(DISTINCT sounded_note) AS pitches,
             max(sounded_note) - min(sounded_note) AS span FROM j GROUP BY 1) t;
```

## Modules holding no samples

120 cataloged modules hold zero `sample_properties` rows (mod 17, it 24, xm 79). Re-parsing all 120
found 2,795 declared samples between them, of which only 115 clear the 512-frame ingest floor, and
those sit in just 8 modules. So 112 of the 120 are chiptunes built from single-cycle waveforms,
correctly excluded by design; the 8 are a genuine gap, most likely stale rows from an ingest
predating a `trackmod` reader improvement. Module browsing already passes over all 120.

## The existing cloud

| | |
|---|---|
| Coordinates persisted | 25,000 |
| Feature vectors persisted | 25,000, all for experiment 2 |
| Experiment 2 | backend `invariant`, label "random 25000 of the real library", 2026-09-07 |

**The live cloud covers 19.6% of the catalog** — a random slice, embedded while the invariant
backend was being validated, never extended to the whole library.

## Storage

The content store is `<library_root>/objects/<hash[:2]>/<hash>.wav`, sharded across 256 directories.

| | |
|---|---|
| `objects/` | 3.9 GB (3.65 GiB), 127,492 files, 256 shard directories, averaging ~33 KB each |
| Database total | 3,162 MB |
| `note_event` | 2,800 MB |
| `sample_spectral_feature` | 106 MB |
| `sample_thumbnail` | 100 MB |
| `sample_feature_vector` | 52 MB |
| `sample` · `sample_properties` · `module_instrument` | 29 MB · 28 MB · 21 MB |

Note events are 89% of the database. If the weak-label work is deferred, so is most of the storage.

## What passes cost

Measured single-core on a 16-core Windows machine, reading from a spinning-disk volume.

| Pass | Cost |
|---|---|
| `PostgresSampleRepository.list_all()` over 127,492 rows | 0.9 s |
| Reading 200 WAVs through `audio_store.read` | 4.86 s → **~52 min for the catalog** |
| Mel spectrogram, `n_fft` 1024, hop 256, 128 mels | **~21.5 min for the catalog** |
| Constant-Q, 108 bins at 12/octave, hop 512 | **~79 min for the catalog** |
| Constant-Q, 216 bins at 24/octave, hop 512 | ~77 min for the catalog |
| Griffin-Lim mel→audio, 32 iterations | **531 ms per sample** |
| Full module re-parse and ingest | ~1.08 s/module ≈ **2.5 h for the corpus** |
| Repeat extraction pass, two concurrent shards | 68 s (8,701 files, 8,657 already known, 44 unparsable) |

Reading the audio dominates every analysis pass, which argues for canonicalizing once into a memmap
and training from that. Constant-Q costs roughly four times mel; both are affordable as one-time
passes, and both parallelize across cores trivially.

## The Griffin-Lim reconstruction experiment

Run here so the incoming work starts with a number rather than an assumption. 60 real samples
between 4,000 and 120,000 frames, peak-normalized, analyzed at `n_fft` 1024 / hop 256 / 128 mels,
inverted with `librosa.feature.inverse.mel_to_audio` at 32 iterations, and compared in the log-mel
domain against the original. The scale is set by the same measure taken between unrelated samples.

| | median | p90 | extreme |
|---|---|---|---|
| Griffin-Lim(32) reconstruction | **4.72 dB** | 9.25 dB | max 12.14 dB |
| Two unrelated real samples | **22.70 dB** | — | p10 16.95 dB, min 11.31 dB |

The reconstruction sits 4.8× closer to its original than a typical unrelated sample does, and the
worst reconstruction still beats the closest unrelated pair. **What this establishes:** a
mel-analysis / mel-synthesis round trip preserves far more than the distances a model has to
represent, so the framing is sound and the bottleneck to watch is the codec.

**What this does not establish, and the caveat must travel with the number:** log-mel RMSE is
computed on magnitudes, so it is blind to phase — and phase is exactly what Griffin-Lim estimates
and exactly where it fails, by smearing transients. On a corpus whose median sound lasts 0.7
seconds and is often a drum hit, that is the failure mode that matters. Only listening settles it,
which is what Stage 2 in [`04-roadmap.md`](04-roadmap.md) is for.

## Inversion primitives already available

No new dependency is needed to build and invert a spectral representation. Installed today:
`librosa.griffinlim`, `librosa.icqt`, `librosa.griffinlim_cqt`,
`librosa.feature.inverse.mel_to_audio`, and `umap.UMAP.inverse_transform` (librosa 1.0.0, numpy
2.5.2, scipy 1.18.1, scikit-learn 1.9.0).
