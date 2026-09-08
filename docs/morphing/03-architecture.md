# The `samplemorph` package

A specification, not a description — none of this exists yet. It follows from
[`02-representation.md`](02-representation.md), and it is shaped by one requirement the user stated
directly: every approach must be pluggable, so that one can be swapped for another and measured
without disturbing anything around it.

## Where it sits

A fifth package beside `samplecore`, `sampleextract`, `samplecloud` and `sampleserver`, depending on
`samplecore` alone. The proposed row for `docs/architecture.md`'s package map:

> `samplemorph` — The decodable-representation pipeline: canonicalizing a sample into a fixed-size
> sound image and its conditioners, a pluggable `SampleCodec` that encodes an image to a latent and
> decodes it back, a pluggable `Vocoder` turning a magnitude representation into audio, and the
> morph that combines two samples' latents at a chosen weight. Codecs also satisfy `samplecloud`'s
> `FeatureExtractor` protocol, so a trained latent reaches the sample cloud through the existing
> embedding pipeline. Depends on `samplecore` only. — *Depends on:* `samplecore`, `sqlalchemy`,
> `librosa`, `scipy`, `torch` (the `morph` extra)

`samplecloud` keeps its ownership as written: descriptors, UMAP, and the promoted spectral vector.
The new package owns codes and audio synthesis. Both feed the same tables.

## Registering a fifth package

More than one file has to learn about it, and `make lint` fails on any of them being missed:

- `pyproject.toml`: `[project.optional-dependencies] morph`, `[project.scripts]`,
  `[tool.importlinter] root_packages`, a new contract (below), `[tool.isort] known_first_party`,
  `[tool.coverage.run] source`.
- `docs/architecture.md`: one package-map row, one bullet under the boundaries section.
- `Makefile`: targets in the house style, plus their `-dev` counterparts.
- `README.md`: a mention alongside the other pipelines.
- `src/samplemorph/py.typed`, force-included in `[tool.hatch.build.targets.wheel.force-include]`.

### The import-linter contracts

Three contracts exist today. `samplecore` may have no dependents among its peers; `sampleserver`
may import neither `sampleextract` nor `samplecloud`; `sampleextract` and `samplecloud` are
independent of each other. Guideline 11 under Shared Ownership calls these load-bearing rather than
advisory.

Two additions:

```toml
[[tool.importlinter.contracts]]
name = "extraction and the morph pipeline stay independent"
type = "independence"
modules = ["sampleextract", "samplemorph"]
```

and the server contract widens to name what stays out of the API process:

```toml
forbidden_modules = ["sampleextract", "samplecloud", "samplemorph.training"]
```

That phrasing is deliberate. A morph route has to decode on request, so the server must reach a
codec; what it must never reach is the training machinery and its dependency weight. Torch-backed
codecs therefore **probe availability at runtime and degrade gracefully**, which is the pattern
Shared Ownership guideline 10 already requires for a heavy third-party boundary. A server without
torch installed serves everything else and reports the morph route as unavailable.

`samplecloud` and `samplemorph` are left free to import each other, because a codec adapting itself
to `FeatureExtractor` is the point of the design. If that turns out to invite trouble, the adapter
moves to `samplecloud` and a third independence contract goes in.

## The four swappable axes

Each is a `Protocol` in its own module, with a registry mirroring `BACKEND_REGISTRY` in
`src/samplecloud/cli.py` — a `Final` dict from name to factory, whose keys feed argparse directly as
`choices=sorted(REGISTRY)`. Adding an approach means adding a class and one registry entry.

### `Canonicalizer` — waveform ↔ sound image

Turns a waveform into the fixed-size `SoundImage` of
[`02-representation.md`](02-representation.md), and back. Implementations: a mel canonicalizer and a
constant-Q canonicalizer, which is the experiment that decides the frequency axis.

### `SampleCodec` — image ↔ latent

`encode` and `decode`, plus `fit` for the ones that learn. Implementations, cheapest first: PCA
(linear and exactly invertible, the honest floor), NMF (nonnegative, often kinder to magnitude
spectra under interpolation), and a conditional VAE.

A codec that works in the waveform domain — RAVE, later — implements `SampleCodec` directly and uses
no canonicalizer and no vocoder at all. The mel-family composition is a *provided* arrangement of the
axes, never a shape every codec is forced into.

### `Vocoder` — magnitude → waveform

Griffin-Lim first, since `librosa.griffinlim`, `librosa.griffinlim_cqt`, `librosa.icqt` and
`librosa.feature.inverse.mel_to_audio` are already installed and need no new dependency. A learned
inverse later, if the listening test says phase is the bottleneck.

Keeping this axis separate from the codec is what makes the Griffin-Lim question answerable at all:
hold the codec fixed, swap the vocoder, and the difference is attributable.

### `Morpher` — two representations and a weight → one

`morph(a, b, weight)`. The default is linear interpolation of the latent; spherical interpolation
and spectral transport are alternatives worth measuring. Isolating this axis means the question
"is the morph bad because the latent is bad, or because the interpolation is naive?" has an
experiment behind it.

### `SoundImage`

The canonical array plus its conditioners — frequency translation in semitones, log canonical
duration, log gain — as a frozen model. It is the currency every axis trades in.

## Storage: no new tables

The catalog already has the shape this needs.

- **Latents are `sample_feature_vector` rows.** `ARRAY(Double)`, primary key
  `(experiment_id, sample_hash)`, written through `PostgresSampleFeatureVectorRepository.insert_many`
  with a `COPY`-based bulk insert. Two experiments hold independent vectors for the same sample, so
  a codec and a descriptor coexist without collision.
- **A run is an `Experiment` row.** `backend_name`, a human `label`, and `params`.
- **`Experiment.params` is plumbed and unused.** `resolve_experiment` accepts it, the repository
  round-trips it as structured JSON, and no caller has ever populated it. It is the natural home for
  a codec's configuration and the identity of the checkpoint that produced the vectors.
- **A codec adapted to `FeatureExtractor` gets the cloud for free.** `extract_features` and
  `reduce_and_persist_coordinates` take the extractor as an injected parameter and care about
  nothing else, so `samplecloud --backend <codec>` places a learned latent in the cloud with no
  change to the embedding pipeline.

Two things do need somewhere to live:

- **Checkpoints.** One new `LibraryConfig` field, pointing outside the repository — beside
  `library_root`, which is where large machine-specific artifacts already go.
- **Runs, metrics and curves.** Outside the repository entirely. MLflow is the candidate the user
  raised, as an optional extra with its tracking store in a gitignored directory. Keep the division
  clean: a Postgres `Experiment` row is the *published* identity of a model whose vectors the
  application reads; MLflow records the *training process*. Neither duplicates the other.

The registry signature differs from `samplecloud`'s for one reason worth stating: its
`Callable[[], FeatureExtractor]` takes no arguments, so a trained codec has nowhere to receive a
checkpoint path. The morph registries take parameterized factories.

## Serving a morph

`GET /samples/{hash}/audio` is a `FileResponse` over a content-addressed path
(`src/sampleserver/routers/samples.py`), and every catalog connection the server opens is read-only
by deliberate design; only the curation routes hold a writable one, reaching the `curation` schema
alone. A synthesized morph belongs to no hash and has no file, so it is genuinely new surface.

Two options, to be decided when the audio is worth serving:

- **Stream it.** A route taking two hashes and a weight, synthesizing and returning bytes. Simple,
  stateless, and it costs a synthesis per request — Griffin-Lim at 32 iterations measured 531 ms per
  sample, so this is interactive but not instant.
- **Cache it content-addressed.** Hash the rendered bytes and write into the same object store, so
  the second request for the same morph is a static file. It gives the result an identity that the
  existing player and preview hooks already know how to handle, at the cost of the first write path
  into the audio store from the server.

## The frontend already has the gesture

The two-sample selection this feature needs was built for the spectral-distance readout:

- Shift-clicking a cloud point calls `onCompare`, which `CloudPanel` routes to `setComparisonSample`
  in `frontend/src/workspace/selectionStore.ts`. Double-clicking focuses a sample instead, so the
  two slots fill independently and neither steals the other.
- `frontend/src/workspace/panels/SpectralDistanceReadout.tsx` renders only once both slots are
  filled, and already shows the pair and their distance. A weight slider belongs beside it.

One coupling has to be generalized. Both players build their URL from a hash:
`useWaveformPlayer(sampleAudioUrl(sampleHash), ...)` at `frontend/src/samples/WaveformPlayer.tsx:48`,
and `audioElement.src = sampleAudioUrl(sampleHash)` at
`frontend/src/samples/useAudioPreview.ts:44`. Taking a URL instead of a hash at those two call sites
is the minimum change needed to play generated audio. `useWaveformPlayer` already recreates its
instance when the URL changes, which is exactly the behavior a moving weight slider wants.

## Facts about this codebase that would otherwise cost a day

Each of these has bitten someone or is positioned to.

**The stored WAV header rate is fiction.** `audio_store.write` stamps every object with
`NOMINAL_WAV_RATE = 44100` regardless of content. The real reference rate is
`sample_properties.rate`, per occurrence, and it means "the rate this waveform is read at when
tracker C-5 is pressed". This applies to every tracker format: XM's `relative_note` and `finetune`
are already folded into `rate` by the reader, and MOD's finetune byte likewise, so the raw tuning
fields are never needed.

**Sounding rate.** `sounding_rate_hz(reference_rate_hz=rate, sounded_note=note)` in
`src/samplecore/pitch.py` gives `rate * 2 ** ((note - 60) / 12)`. Tracker C-5 is note value 60 and
equals MIDI 72.

**`SampleDetail.duration_seconds` is wrong for real durations.** It is computed as
`frames / NOMINAL_WAV_RATE`, so it reports the duration at the fictional rate. Use
`frames / dominant_rate_hz`.

**PCM shape.** `SamplePCM.pcm` is always 2-D, `(frames, channels)`, float64 in `[-1, 1]`. Mono is
`(frames, 1)`, never 1-D. The house mixdown is `pcm.mean(axis=1)`. Dequantized 8-bit values land in
`[-1.0, 0.9921875]` — exactly `+1.0` is never produced, by one least-significant bit.

**`audio_store.read` is eager, and always float64.** It reads the whole file in one call with no
caching, and `dequantize` widens to float64 whatever the stored depth was. Holding the decoded
corpus in memory therefore costs four times its on-disk size for 16-bit content and eight times for
8-bit — **about 23 GB** for this catalog's 2.93 billion frames, against 3.9 GB on disk. **Cast to
float32 immediately after reading**; nothing downstream in this repository needs the extra
precision.

Reading measured ~52 minutes single-core over 127k samples and is the dominant cost of any analysis
pass. Per-epoch random access over 127,492 small files is dominated by filesystem overhead rather
than by bytes, so canonicalize once into a memmap and train from that.

**`note_event` has no `sample_hash`.** Reaching a sample means joining through
`(module_id, instrument_index, sample_slot)` against `sample_properties`; the composite index
`note_event_occurrence_index` serves it. A note event is a key press with no note-off and no
duration, and `pattern_index` is storage order rather than playback order, since no order list is
stored.

**Two repository methods break at catalog scale.** `PostgresSampleRepository.get_many` and
`PostgresNoteEventRepository.dominant_note_by_hash` build unchunked `IN` clauses, which exceed
Postgres's 65,535-parameter limit above about 65k hashes. `names_and_rates_by_hash` and
`instrument_names_by_hash` *are* chunked at 20,000. For a whole-catalog pass, a single unfiltered
scan of `sample_properties` beats any of them.

**Open a training connection read-only.** `connect(url, read_only=True)` skips schema creation and
sets the session read-only. `open_catalog_connection` always opens writable, which a read-only pass
has no use for.

**Similarity is brute force.** `GET /samples/{hash}/similar` loads the whole
`sample_spectral_feature` table per request. It works at 25,000 rows; at 127,492 it will need an
index structure.

## Tests

Mirror `src/samplemorph/` under `tests/samplemorph/`, following the house idioms: full-sentence test
names describing the asserted behavior, frozen dataclass cases parametrized over a single `case`
argument, protocol-shaped stubs written by hand rather than `unittest.mock`, and real Postgres
through the `connection` fixture for anything touching storage. `tests/samplecloud/test_features.py`
is the closest model for testing a pipeline stage against a stub extractor.

Coverage is gated at 90% over the packages named in `[tool.coverage.run] source`, enforced on
`make coverage`. Adding `samplemorph` there means its code counts toward that gate.
