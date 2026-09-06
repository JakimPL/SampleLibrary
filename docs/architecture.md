# Architecture & Ownership

SampleLibrary turns a personal collection of tracker modules into a browsable, deduplicated
sample library: a DuckDB catalog of modules, samples, and their tracker-specific properties; a
content-addressable store of extracted audio; detected equivalence classes between near-duplicate
samples; and a web application for navigating and visualizing all of it. The project has two
natures — an offline, batch-oriented extraction/analysis tool, and a served read-only web app —
kept as four packages under one `pyproject.toml` so each keeps its own dependency footprint and
its own write/read boundary, enforced by the `[tool.importlinter]` contracts in `pyproject.toml`.

## Package map (`src/`)

| Package | Owns | Depends on |
|---|---|---|
| `samplecore` | The domain models (`Module`, `Sample`, `SampleProperties` and its tracker-specific subtypes, `SampleRelation`, `EquivalenceClass`, `SampleSpectralFeature`), the DuckDB schema and connection helpers, the content-addressable audio store, sample hashing, equivalence-class grouping, spectral-distance computation, and the local `LibraryConfig` loader. A leaf: nothing else in this repository. | `duckdb`, `sqlalchemy`, `numpy`, `pydantic`, `soundfile` |
| `sampleextract` | The offline extraction pipeline: walking the module source directory, parsing modules via `trackmod`, rendering sample audio to the content store, populating the DuckDB catalog, computing cached waveform-preview thumbnails (inline at ingest, and via a standalone backfill pass), and the equivalence-class detection pass. | `samplecore`, `sqlalchemy`, `trackmod`, `tqdm` |
| `samplecloud` | The offline embedding pipeline for the sample-cloud visualization: pluggable feature extraction (`FeatureExtractor` protocol), UMAP dimensionality reduction (explicit Euclidean metric), persistence of raw feature vectors (Parquet), and persistence of each sample's standardized vector and 2D coordinate (DuckDB) -- the standardized vector is `samplecore`'s own named spectral-distance metric, reused by `sampleserver`'s distance endpoints. Depends on `samplecore` only, never on `sampleextract`, so a future heavy embedding backend's dependencies never reach the extraction pipeline or the web server. | `samplecore`, `sqlalchemy`, `librosa`, `umap-learn`, `scikit-learn` (the `cloud` extra) |
| `sampleserver` | The FastAPI read API serving the catalog, cross-references, equivalence classes, spectral distances, stats, and cloud coordinates to the frontend. Opens its DuckDB connection read-only, so a bug in a route handler cannot corrupt the library. | `samplecore`, `sqlalchemy`, `fastapi`, `uvicorn` (the `server` extra) |

## Boundaries the import-linter contracts enforce

- `samplecore` has no dependents among its peers: nothing it does can accidentally couple to the
  extraction pipeline, the embedding pipeline, or the web server.
- `sampleserver` never imports `sampleextract` or `samplecloud`: the read API cannot trigger a
  batch job, and cannot inherit either pipeline's heavier dependencies.
- `sampleextract` and `samplecloud` are declared independent of each other: extraction never waits
  on embedding, and a change to one pipeline's dependencies never touches the other.

## Persistence

DuckDB is the single authoritative store for all catalog metadata (`Module`, `Sample`,
`SampleProperties` together with its per-tracker `xm_sample_properties`/`it_sample_properties`/
`s3m_sample_properties` tables (MOD carries no properties beyond the shared base, so it has no
table of its own), `SampleRelation`, `sample_cloud_coordinates`, `module_cloud_coordinates`,
`sample_spectral_feature`, and `sample_thumbnail`). Equivalence classes are not a stored table:
`samplecore.equivalence_classes` derives them on request from `SampleRelation` rows, since the
relation graph stays small even at real-catalog scale. The filesystem content-addressable store —
`{library_root}/objects/{hash[0:2]}/{hash}.wav`, one file per unique `Sample` — is the single
authoritative store for audio bytes. Neither is a cache of the other, except that `Sample` rows
could in principle be rebuilt by rehashing the store; that is a recoverability property, not a
substitute for backing up the `.duckdb` file itself.

Local, machine-specific paths (the module source directory, the library root) are read from a
gitignored `config.toml` via `samplecore.config.load_config`, never hardcoded into source.
`config.example.toml` documents the expected shape.

## Extending to new tracker formats

`sampleextract`'s format dispatch is a small registry (module suffix → loader function), not
branching logic; MOD and S3M (added once `trackmod`'s own readers for both were already complete)
extended it with two registry entries each. Each format gets a member of the `TrackerFormat` enum,
both schema-level and reachable through `module.tracker`'s `CheckConstraint`, and a tracker-specific
properties table for whatever it stores beyond the shared `sample_properties` base -- `xm_sample_properties`
(tuning), `it_sample_properties` (global volume, sustain loop, filename, vibrato), and
`s3m_sample_properties` (filename). MOD gets no properties table at all: TrackMod's MOD reader folds
its finetune byte straight into the shared `rate` field and keeps no separate raw copy, and the
format stores no per-sample panning, sustain loop, filename, or vibrato of its own, so
`MODSampleProperties` carries nothing beyond the shared base -- a format's own subtype and
discriminator tag are added regardless of whether it turns out to need a child table. The content
store and the API's read shape stay as they are: content addressing and the served response models
are already format-agnostic.
