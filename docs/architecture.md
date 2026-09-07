# Architecture & Ownership

SampleLibrary turns a personal collection of tracker modules into a browsable, deduplicated
sample library: a Postgres catalog of modules, samples, and their tracker-specific properties; a
content-addressable store of extracted audio; detected equivalence classes between near-duplicate
samples; and a web application for navigating and visualizing all of it. The project has two
natures — an offline, batch-oriented extraction/analysis tool, and a served read-only web app —
kept as four packages under one `pyproject.toml` so each keeps its own dependency footprint and
its own write/read boundary, enforced by the `[tool.importlinter]` contracts in `pyproject.toml`.

## Package map (`src/`)

| Package | Owns | Depends on |
|---|---|---|
| `samplecore` | The domain models (`Module`, `Sample`, `SampleProperties` and its tracker-specific subtypes, `SampleRelation`, `Experiment`, `SampleFeatureVector`, `EquivalenceClass`, `SampleSpectralFeature`, `NoteEvent`, `ModuleInstrument`, `SampleLabel`), the Postgres schema and connection helpers, the content-addressable audio store, sample hashing, equivalence-class grouping, spectral-distance computation, the anchoring rule that keeps a hand label attached to its sample, and the local `LibraryConfig` loader. A leaf: nothing else in this repository. | `psycopg`, `sqlalchemy`, `numpy`, `pydantic`, `soundfile` |
| `sampleextract` | The offline extraction pipeline: walking the module source directory, parsing modules via `trackmod`, rendering sample audio to the content store, populating the Postgres catalog, computing cached waveform-preview thumbnails, reading each module's patterns for the notes they play (both inline at ingest, and via a standalone backfill pass each), the equivalence-class detection pass, and moving hand labels in and out of the catalog. | `samplecore`, `sqlalchemy`, `trackmod`, `tqdm` |
| `samplecloud` | The offline embedding pipeline for the sample-cloud visualization: pluggable feature extraction (`FeatureExtractor` protocol) scoped to a named `Experiment` so more than one backend or parameter set can extract concurrently without clobbering another's vectors, UMAP dimensionality reduction (explicit Euclidean metric) over one chosen experiment, and persistence of each sample's standardized vector and 2D coordinate -- the standardized vector is `samplecore`'s own named spectral-distance metric, reused by `sampleserver`'s distance endpoints. Depends on `samplecore` only, never on `sampleextract`, so a future heavy embedding backend's dependencies never reach the extraction pipeline or the web server. | `samplecore`, `sqlalchemy`, `librosa`, `umap-learn`, `scikit-learn` (the `cloud` extra) |
| `sampleserver` | The FastAPI API serving the catalog, cross-references, equivalence classes, spectral distances, stats, and cloud coordinates to the frontend, plus the curation routes recording a person's own sample labels. Every catalog read opens its Postgres connection read-only, so a bug in a route handler cannot corrupt the library; the curation routes hold the one writable connection, and it reaches only the `curation` schema's own tables. | `samplecore`, `sqlalchemy`, `fastapi`, `uvicorn` (the `server` extra) |

## Boundaries the import-linter contracts enforce

- `samplecore` has no dependents among its peers: nothing it does can accidentally couple to the
  extraction pipeline, the embedding pipeline, or the web server.
- `sampleserver` never imports `sampleextract` or `samplecloud`: the read API cannot trigger a
  batch job, and cannot inherit either pipeline's heavier dependencies.
- `sampleextract` and `samplecloud` are declared independent of each other: extraction never waits
  on embedding, and a change to one pipeline's dependencies never touches the other.

## Persistence

Postgres is the single authoritative store for all catalog metadata (`Module`, `Sample`,
`SampleProperties` together with its per-tracker `xm_sample_properties`/`it_sample_properties`/
`s3m_sample_properties` tables (MOD carries no properties beyond the shared base, so it has no
table of its own), `SampleRelation`, `Experiment`, `sample_feature_vector`,
`sample_cloud_coordinates`, `module_cloud_coordinates`, `sample_spectral_feature`,
`sample_thumbnail`, `module_instrument`, `note_event`, and `module_note_extraction`). Equivalence classes are not a stored table: `samplecore.equivalence_classes`
derives them on request from `SampleRelation` rows, since the relation graph stays small even at
real-catalog scale. The filesystem content-addressable store —
`{library_root}/objects/{hash[0:2]}/{hash}.wav`, one file per unique `Sample` — is the single
authoritative store for audio bytes. Neither is a cache of the other, except that `Sample` rows
could in principle be rebuilt by rehashing the store; that is a recoverability property, not a
substitute for backing up the catalog itself.

`sample_feature_vector` holds one `FeatureExtractor` backend's raw output per sample, scoped to an
`Experiment` row (its backend name, parameters, and a human label) rather than a single global
table: two experiments extracting concurrently write disjoint rows, keyed by
`(experiment_id, sample_hash)`, so neither can clobber the other's vectors. `sample_cloud_coordinates`,
`module_cloud_coordinates`, and `sample_spectral_feature` stay singular and global -- they represent
whichever experiment has been deliberately *promoted* (`samplecloud.reduce.reduce_and_persist_coordinates`,
given an explicit `experiment_id`), not per-experiment scratch space.

`note_event` holds one row per key a module's patterns press, keyed by its grid position
`(module_id, pattern_index, row_index, channel_index)`. Beside the key a cell states, each row
carries the note it actually sounds and the occurrence it reaches, which an instrument's keymap
decides: a keymap routes a key onto a sample *and* the note that sample sounds at, so the key a
composer wrote and the pitch a listener hears are separate values, and Impulse Tracker is the format
that regularly makes them differ. Extraction consumes the keymap and records its outcome, which is
what lets a reader reach the pitch a sample is heard at without holding a routing table of its own.
The sounding rate follows from that note and the occurrence's own rate
(`rate * 2 ** ((sounded_note - 60) / 12)`, tracker C-5 being the rate's reference key), so it is
computed where it is needed. A key reaching a sample below `minimum_sample_frames` keeps its note and
leaves its slot open, since the catalog holds no occurrence to name; a cell stating no instrument
leaves both open, its routing being a fact about how the song is played rather than what the cell
holds. `module_instrument` records each voice slot the same numbering addresses, and its names feed
`classify_sample_category` alongside the occurrence names -- a tracker names an instrument apart from
the waveforms its keys reach, so a sample stored as "smp03" is described only there.
`module_note_extraction` records which modules have been read, so a module whose patterns press no
keys still reads as finished and a resumed pass spares it a second parse.

## Hand-curated work

`curation.sample_label` holds the category a person chose for a sample, and it is the one thing in
this library no pass can rebuild. It therefore sits on a `MetaData` of its own, in a Postgres schema
of its own (`samplecore.storage.curation`), apart from the single `MetaData` every other table
belongs to. Both places this project empties a database — `scripts/reset_library.py` and the test
suite's own teardown — iterate `database.metadata.sorted_tables`, so a table registered on the
curation metadata is beyond their reach by construction rather than by an exemption list somebody
has to keep current. For the same reason it carries no foreign key into the catalog: one would
either delete these rows along with the samples or block the purge outright. A test in
`tests/scripts/test_reset_library.py` pins exactly that, seeding a label and asserting it survives a
full reset.

Because a sample's hash follows from how this project hashes audio, a label keyed on the hash alone
would be lost the moment that changes. Every label therefore also records the module slot it was
chosen from — module hash, filename, instrument index, sample slot, and the occurrence's name — and
`samplelabels relink` reads those slots back to recover whatever sample sits there now. The label is
stored per sample even when it was applied to a whole equivalence class at once, since a class is
identified by a content hash over its members and gains a different identity the moment its
membership changes; `source` records which gesture applied it, so a decision made about one sample
stays distinguishable from one inherited from its near-duplicates.

`samplelabels export` writes every label to JSONL as the copy that outlives the database, and
`import` merges a file back without clearing anything.

Local, machine-specific configuration (the module source directory, the library root, the catalog's
connection URL) is read from a gitignored `config.toml` via `samplecore.config.load_config`, never
hardcoded into source; the connection URL can also be supplied via the `SAMPLELIBRARY_DATABASE_URL`
environment variable (taking precedence over the config file), so credentials need not live in a
file at all. `config.example.toml` documents the expected shape.

A repository that recomputes a whole table's contents from scratch every run -- the cloud
coordinate, module coordinate, and spectral feature repositories, whenever a fresh embedding pass
replaces every row -- exposes `replace_all` alongside its per-row `upsert`: clear the table, then
bulk-load every row through `samplecore.storage.database.bulk_insert`, never a loop of individual
upserts. Parameterized per-row inserts (`executemany`, one large multi-row `VALUES` statement) were
measured at the same few-milliseconds-per-row cost regardless of batch size under this project's
previous engine, turning tens of thousands of rows into minutes; `bulk_insert` reaches past
SQLAlchemy's `Connection` for the underlying `psycopg` connection and streams rows through
Postgres's own `COPY ... FROM STDIN`, avoiding that per-row cost entirely without assuming the
client and server share a filesystem the way a file-path-based `COPY` would.

## Deployment

`sampleserver` is the only package meant to run as a long-lived service; `sampleextract` and
`samplecloud` are one-shot offline batch scripts, run by hand or on a schedule, never by the served
app itself. The root `Dockerfile` builds a runtime image for `sampleserver` alone, installing only
the `server` extra (`fastapi`, `uvicorn`) -- `sampleextract`/`samplecloud`'s own heavier
dependencies (`librosa`, `umap-learn`, `scikit-learn`) never reach that image, mirroring the
`sampleserver never imports the offline batch pipelines` import-linter contract above.
`docker-compose.yml` adds a `postgres` service alongside it (a named volume for persistence), as a
worked example of the two running together; a real deployment points
`database_url`/`SAMPLELIBRARY_DATABASE_URL` at whatever Postgres instance it actually runs against,
container or otherwise. Local development runs against a Postgres installed on the machine directly,
which the test suite and both library databases share -- see README.md. The container runs multiple
`uvicorn` worker processes (`--workers`, not `--reload`) rather than the single-process dev server
`make serve` starts: each worker opens its own read-only Postgres connection per request
(`sampleserver.dependencies.get_connection`), which Postgres's own concurrent-connection handling
supports natively, so multiple people browsing the library through one deployed server works
correctly with no shared state between workers. The library's data directory and a `config.toml`
pointing at its in-container path are supplied at `docker run` time (a bind mount plus
`SAMPLELIBRARY_CONFIG`), never baked into the image, mirroring `config.toml` never being committed
to the repository.

Postgres supports genuine concurrent readers *and* writers against the same database, unlike this
project's previous engine (DuckDB), which excluded every other connection -- read-only included --
while one process held a write transaction open. A batch job (`sampleextract`, `sampleequivalence`,
`samplethumbnail`, `samplecloud`) can now run alongside `sampleserver` serving live traffic without
that exclusion; the operational concern that remains is a batch job's own resource footprint on the
host machine (CPU contention, not lock contention -- still worth timing a heavy local run
accordingly). `samplecloud` in particular writes into its own experiment
(`sample_feature_vector`, scoped by `experiment_id`) and never touches `sample_cloud_coordinates`
until `reduce_and_persist_coordinates`'s own explicit promotion step, so an in-progress extraction
run has no visible effect on what the server or other experiments see until that promotion happens.

## Sample cloud embeddings

`samplecloud.backends.FeatureExtractor` is a protocol, not a fixed implementation: anything
returning a fixed-length, finite vector for a waveform fits the pipeline, so the extraction method
stays swappable as perceptual results call for a different approach. `LibrosaFeatureExtractor` is
the current implementation, combining a whole-clip timbral summary (MFCC, spectral centroid and
bandwidth, zero-crossing rate, RMS, each aggregated by mean and standard deviation across frames)
with temporal features that keep a sound's shape over time visible in the vector: segment-wise
means across early/mid/late thirds of the clip, a duration-normalized attack-time fraction from
onset detection, and delta-MFCC statistics capturing how fast timbre moves. The projection and the
persisted "spectral distance" both derive directly from this vector's length and composition, so
changing it -- adding, removing, or reweighting a feature group -- changes what similarity means
for the whole library. Because every extraction run is scoped to its own `Experiment`, this no
longer risks mixing incompatible vector shapes the way a single shared cache once did: run the
changed extractor as a new experiment (`samplecloud --backend <name>`), inspect and compare its
result, and only promote it (`reduce_and_persist_coordinates` against that experiment's id) once
satisfied -- the previously promoted experiment's `sample_cloud_coordinates` stay exactly as they
were until that deliberate step.

## Sample categorization

`SampleCategory` (`samplecore.models.category`) is a coarse, guessed instrument role -- kick,
snare, bass, and so on -- attached to every sample summary, detail, and cloud point. It is not a
stored column: mirroring equivalence classes, `samplecore.categorization.classify_sample_category`
derives it at read time from the sample's own occurrence names, the same name data
`samplecore.naming.choose_dominant_name` already reads to resolve `display_name`. Classification is
one plain, ordered keyword table matched against each name with its separators stripped, deliberately
a first-pass heuristic rather than a tuned classifier -- expect to retune the keyword table against
how well it agrees with real listening. A hand label wins wherever one exists (`SampleSummary.hand_label`,
and the same field on the detail and cloud-point models): the guessed category travels beside it, so
a reader sees both what a person decided and what the keyword table inferred, and `CategoryBadge` is
the single place that rule is applied. The frontend colors the sample cloud by category
(`regl-scatterplot`'s own categorical coloring, one fixed hue per `SampleCategory` declared as a CSS
custom property per theme in `styles.css`) and shows the category as a badge everywhere a sample's
name appears; the same color and label always travel together, since fourteen categories are too
many to stay reliably distinguishable by hue alone for every viewer. The cloud keeps colouring by
the guessed category for that same reason: a hand label is free text, so it belongs to an unbounded
set of hues, and it wears one style of its own in the badge instead.

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
