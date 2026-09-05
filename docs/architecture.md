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
| `samplecore` | The domain models (`Module`, `Sample`, `SampleProperties` and its tracker-specific subtypes, `SampleRelation`), the DuckDB schema and connection helpers, the content-addressable audio store, sample hashing, and the local `LibraryConfig` loader. A leaf: nothing else in this repository. | `duckdb`, `numpy`, `pydantic`, `soundfile` |
| `sampleextract` | The offline extraction pipeline: walking the module source directory, parsing modules via `trackmod`, rendering sample audio to the content store, populating the DuckDB catalog, computing cached waveform-preview thumbnails (inline at ingest, and via a standalone backfill pass), and the equivalence-class detection pass. | `samplecore`, `trackmod`, `tqdm` |
| `samplecloud` | The offline embedding pipeline for the sample-cloud visualization: pluggable feature extraction (`FeatureExtractor` protocol), UMAP dimensionality reduction, and persistence of feature vectors (Parquet) and coordinates (DuckDB). Depends on `samplecore` only, never on `sampleextract`, so a future heavy embedding backend's dependencies never reach the extraction pipeline or the web server. | `samplecore`, `librosa`, `umap-learn`, `scikit-learn` (the `cloud` extra) |
| `sampleserver` | The FastAPI read API serving the catalog, cross-references, equivalence classes, stats, and cloud coordinates to the frontend. Opens its DuckDB connection read-only, so a bug in a route handler cannot corrupt the library. | `samplecore`, `fastapi`, `uvicorn` (the `server` extra) |

## Boundaries the import-linter contracts enforce

- `samplecore` has no dependents among its peers: nothing it does can accidentally couple to the
  extraction pipeline, the embedding pipeline, or the web server.
- `sampleserver` never imports `sampleextract` or `samplecloud`: the read API cannot trigger a
  batch job, and cannot inherit either pipeline's heavier dependencies.
- `sampleextract` and `samplecloud` are declared independent of each other: extraction never waits
  on embedding, and a change to one pipeline's dependencies never touches the other.

## Persistence

DuckDB is the single authoritative store for all catalog metadata (`Module`, `Sample`,
`SampleProperties`, `SampleRelation`, `sample_cloud_coordinates`, and `sample_thumbnail`). The
filesystem content-addressable store — `{library_root}/objects/{hash[0:2]}/{hash}.wav`, one file
per unique `Sample` — is the single authoritative store for audio bytes. Neither is a cache of the
other, except that `Sample` rows could in principle be rebuilt by rehashing the store; that is a
recoverability property, not a substitute for backing up the `.duckdb` file itself.

Local, machine-specific paths (the module source directory, the library root) are read from a
gitignored `config.toml` via `samplecore.config.load_config`, never hardcoded into source.
`config.example.toml` documents the expected shape.

## Extending to new tracker formats

`sampleextract`'s format dispatch is a small registry (module suffix → loader function), not
branching logic, specifically so that adding MOD and S3M later is additive: a new `trackmod`
tracker package plus two registry entries, with no structural change to the catalog schema, the
content store, the API, or the frontend.
