# Prior research

A secondary reference, carried across so the reasoning can be audited rather than taken on trust.
These are earlier findings recorded close to their original wording. Where a later measurement
supersedes one, the correction is stated inline rather than by editing the original away.

None of this needs to be read to start work. It is here for when a conclusion in
[`02-representation.md`](02-representation.md) or [`06-alternatives.md`](06-alternatives.md) looks
arbitrary and you want to see what it came from.

## The two descriptor backends, compared

Both are implemented and selectable: `samplecloud --backend invariant|librosa`.

Measured against the real library:

| | invariant | librosa |
|---|---|---|
| Transposition retrieval at −12 semitones | **95.5%** | 8.2% |
| Category coherence | 33.8% | **37.9%** |
| Cost | cheaper | — |

**Neither dominates.** The invariant backend wins transposition decisively and is cheaper; librosa
wins category coherence. Three explanations for librosa's edge were proposed and all three refuted
by measurement, and the deficit — concentrated in cymbal, pad and vocal — stays unexplained. The
remaining untested hypothesis is that librosa's 13 MFCCs with mean, standard deviation *and*
frame-to-frame deltas describe spectral-envelope shape and its articulation more finely than the
invariant backend's 20 CQHC coefficients at 8 time points.

**Both figures need re-measuring**, for the reasons in [`05-evaluation.md`](05-evaluation.md): the
scripts behind them were never committed, the vectors came from a 25,000-sample experiment, and the
category figure was computed against labels covering 10.5% of the catalog.

## Invariance findings for the librosa backend

Measured against the real `LibrosaFeatureExtractor` output, standardized by the dev corpus's own
per-dimension deviations — the same `StandardScaler` step `samplecloud.reduce` applies before
persisting. The yardstick for "is this large?" is that corpus's own pairwise standardized-distance
distribution: min 1.52, median 11.64, p90 14.91, max 18.01 across all 465 pairs.

### Rate mislabeling is a real and significant flaw

`audio_store.write` stamps every stored WAV with 44,100 Hz regardless of a sample's true rate, and
`LibrosaFeatureExtractor` analyzes assuming that same rate. The same synthetic tone generated at a
true 8,363 Hz versus 44,100 Hz, both fed through the extractor as-is, land a standardized distance
of **13.66** apart — at the corpus's own p90, as different as the least-similar tenth of genuinely
unrelated real pairs. The error is driven by spectral centroid, bandwidth and MFCC, since the
frequency axis is scaled wrong by the ratio of true to assumed rate.

A correctly-labeled resample round trip (44,100 → 22,050 → 44,100) moves the vector only **0.45**.
**Resampling itself is a non-issue; mislabeling the rate is the actual problem.**

### Trimming degrades gracefully, then falls apart

A 1.0 s stationary tone trimmed to 0.5 s shifts only 3.08, below the corpus's own p10. At 0.1 s it
is 8.61, at 0.02 s it is 11.37 (cosine similarity down to 0.87), and at 0.005 s — under the
extractor's minimum signal length, so zero-padded — it is **19.85**, worse than the corpus's own
*maximum* real pairwise distance.

Two causes compound. A hard cut creates a spurious edge that onset detection can register as a real
attack and that spikes the centroid and bandwidth standard deviations. And standard-deviation
features become noisy small-sample estimates over very few STFT frames. This is a short-clip
statistics-and-padding problem rather than a resampling one.

### Gain is not normalized anywhere

RMS-family dimensions scale directly with amplitude and are never loudness-normalized before
standardization. A plain unclipped gain change moves the standardized vector **9.32** at 0.5× and
**14.02** at 0.25× — already past the corpus median, on par with real clipping distortion (2× gain,
51% of samples clipped, moved 13.15 with cosine similarity down to 0.84 through genuinely new
harmonics).

Zero-crossing rate, spectral centroid and bandwidth, and MFCC coefficients beyond the zeroth are
correctly gain-invariant by construction, holding cosine similarity at 0.994 or better for the
unclipped cases. But the Euclidean nearest-neighbor metric the library actually uses is dominated by
the un-normalized RMS dimensions rather than by those shape dimensions.

## How the rate finding was resolved

The obvious remedy — resample to a true rate, or pass each sample's real rate into the extractor —
was tried and abandoned. **There is no single true rate to resample to.** A real sample hash can
carry many genuinely different declared rates across its occurrences; one was found spanning
7,862–19,073 Hz across twelve occurrences. That is how tracker instruments work rather than an edge
case.

*Later measurement, 2026-09-08:* this affects **6,972 hashes, 5.5% of the catalog**, with a spread
of exactly one octave at the median, seventeen semitones at p90, and six octaves at the extreme. So
it is real and bounded — worth designing around, and not worth over-engineering for.

The user rejected both "pick a rate" and "detect pitch and normalize to it" as framings, the latter
because it fails on percussion, a vital six of fourteen categories. What followed was a validated,
percussion-inclusive, uniform fix with no branching, reaching 28 of 30 across all real categories,
with gain settled via the level and carrier split from the user's own OptiSample project. That work
is what `InvariantFeatureExtractor` is.

## Open descriptor items, none acted on

- **The `+absolute` variant** measured +2.1 points on transposition retrieval and +1.2 on category
  agreement, against −3.8 on bass. A judgment call, not adopted.
- **Multiscale envelope localization for transients** — the user's own idea, untested.
- **A full-catalog re-embed** (127k samples, roughly an hour) was unblocked and never scheduled.
  This is now Stage 1 work in [`04-roadmap.md`](04-roadmap.md).

## The removed morphing spike

A phase-vocoder two-sample blend notebook was built in an earlier session and deleted at the user's
request, including from git history; its commits no longer exist, so there is nothing to find in
`git log` and nothing to resurrect.

The objection was to the approach rather than the implementation: it was a direct two-sample signal
blend, and what the user wants is the ability to reconstruct a sound from a representation. The
embedding-invariance research that grew out of that spike is unaffected and is recorded above.

## Note extraction, as completed

Schema, resolution, ingest wiring, the full backfill, CLI, playback grounding and tests are all
committed. Measured on completion: **8,451 modules, 29,382,000 note events, 244,857 instrument
slots**. Of those events 94.8% resolve to a sounded note, 81.1% reach a cataloged sample occurrence,
5.0% state no instrument at all, and 1.0% sound a different note than the key pressed.

A 60-module pilot had projected roughly 34 million events and an 88.1% resolved share, so **the
pilot ran optimistic by about 14% on volume and 7 points on resolvability**. Size a future
full-corpus estimate from the completed figures rather than from a small random sample.

The pass needed four restarts: the harness kills it whenever system free memory dips, and a
worst-case module materializes about 98,000 note events at once. Resumability — a marker table plus
per-module transactions — is what made that survivable, and any comparable pass wants the same.

What remains from that work: the eight modules genuinely missing their samples, and a tonality
signal aimed at the tonal material the keyword classifier misses. The second is now metric 3 in
[`05-evaluation.md`](05-evaluation.md).
