# Architecture & Ownership

SampleLibrary turns a personal collection of tracker modules into a browsable, deduplicated
sample library: a Postgres catalog of modules, samples, and their tracker-specific properties; a
content-addressable store of extracted audio; detected equivalence classes between near-duplicate
samples; and a web application for navigating and visualizing all of it. The project has two
natures — an offline, batch-oriented extraction/analysis tool, and a served read-only web app —
kept as five packages under one `pyproject.toml` so each keeps its own dependency footprint and
its own write/read boundary, enforced by the `[tool.importlinter]` contracts in `pyproject.toml`.

## Package map (`src/`)

| Package | Owns | Depends on |
|---|---|---|
| `samplecore` | The domain models (`Module`, `Sample`, `SampleProperties` and its tracker-specific subtypes, `SampleRelation`, `Experiment`, `SampleFeatureVector`, `EquivalenceClass`, `SampleSpectralFeature`, `NoteEvent`, `ModuleInstrument`, `SampleAnnotation`), the reading of a hand label as tag paths and the agreement between two of them (`samplecore.labeling`), the Postgres schema and connection helpers, the content-addressable audio store, sample hashing, equivalence-class grouping, spectral-distance computation, the pitch rule that turns an occurrence rate and a pressed key into the one rate a sample is really played at, the anchoring rule that keeps a hand label attached to its sample, the waveform hygiene every analysis shares (folding to mono, the subsonic high-pass), the auditory front end (`samplecore.auditory`: an ERB-spaced gammatone bank, subband envelopes and the two-lobe modulation spectrum a listener hears flutter and roughness on, designed once as data so a numpy reading and a torch loss apply the same kernels), and the local `LibraryConfig` loader. A leaf: nothing else in this repository. | `psycopg`, `sqlalchemy`, `numpy`, `scipy`, `pydantic`, `soundfile` |
| `sampleextract` | The offline extraction pipeline: walking the module source directory, parsing modules via `trackmod`, rendering sample audio to the content store, populating the Postgres catalog, computing cached waveform-preview thumbnails, reading each module's patterns for the notes they play (both inline at ingest, and via a standalone backfill pass each) and folding those notes into the rate each sample is heard at, the equivalence-class detection pass, and moving hand labels in and out of the catalog. | `samplecore`, `sqlalchemy`, `trackmod`, `tqdm` |
| `samplecloud` | The offline embedding pipeline for the sample-cloud visualization: pluggable feature extraction (`FeatureExtractor` protocol) scoped to a named `Experiment` so more than one backend or parameter set can extract concurrently without clobbering another's vectors -- two hand-built descriptors, and a pretrained audio-text model behind the `clap` backend (the `teacher` extra) that hears what people would call alike, teaches the descriptor `samplemorph` trains, and through its text tower suggests labels for every sample from a vocabulary of prompts (`samplecloud.suggestions`, each scoring an `Experiment` of its own), UMAP dimensionality reduction (explicit Euclidean metric) over one chosen experiment, and persistence of each sample's standardized vector and 2D coordinate -- the standardized vector is `samplecore`'s own named spectral-distance metric, reused by `sampleserver`'s distance endpoints. It also owns the evaluation harness (`samplecloud.evaluation`) that scores any experiment's descriptor against the targets the catalog already carries: whether a retuning moves the descriptor, whether it groups what the keyword table names alike, and whether it groups what the note events say the library plays alike. Depends on `samplecore` only, never on `sampleextract`, so a future heavy embedding backend's dependencies never reach the extraction pipeline or the web server. | `samplecore`, `sqlalchemy`, `librosa`, `umap-learn`, `scikit-learn` (the `cloud` extra); `torch`, `transformers` (the `teacher` extra) |
| `samplemorph` | The decodable-representation pipeline: canonicalizing a sample into a fixed-size sound image on a log-frequency by duration-fraction grid together with the three conditioners that image was normalized by (where its content sits in pitch, how long it sounds, and how loud it was), and a pluggable `Vocoder` turning a magnitude spectrogram back into audible frames -- in production a restorer taught what the grid's band averaging removes from this library's own sounds, followed by phase gradient heap integration under a Gaussian analysis -- and a learned `Descriptor` (`samplemorph.descriptors`) that reads the canonical grid as one vector: distilled from the pretrained listening model, taught by retuned views that a retuning changes nothing, and by the hand labels what the listener calls alike. A conditioned codec (`samplemorph.codecs.conditioned`) decodes the grid from that descriptor beside a small residual under a prior, so a morph moves a sound's identity through the space the harness judges and its particulars through a space where every point decodes. The frequency axis is logarithmic, which turns a change of playback rate into a translation along it, so the translation is measured, moved out of the grid, and carried as a conditioner -- which is what leaves the representation invertible where the sample cloud's descriptors are not. Training passes (`samplemorph.training`) run under a run tracker and read a grid cache canonicalized once under the library root. Each shell command is one module under `samplemorph.commands`, and the ones that train import the trainer only when they run, so parsing arguments and the commands that train nothing stay clear of it. `samplemorph.service` is the same pipeline over HTTP: the morph inference process (`samplemorph-serve`), which loads the fitted models once, renders any point between two stored samples on request, and is what the web API dials for a morph. Depends on `samplecore` only. | `samplecore`, `librosa`, `scikit-learn`, `torch`, `fastapi`, `uvicorn` (the `morph` extra) |
| `sampleserver` | The FastAPI API serving the catalog, cross-references, equivalence classes, spectral distances, stats, and cloud coordinates to the frontend, plus the curation routes recording a person's own decisions about samples, and the morph routes, which relay renders from the inference process over HTTP. Every route is served under `API_PREFIX` (`/api`), which keeps the whole API inside one path segment and leaves every other path to the single-page application's own routes. Every catalog read opens its Postgres connection read-only, so a bug in a route handler cannot corrupt the library; the curation routes hold the one writable connection, and it reaches only the `curation` schema's own tables. | `samplecore`, `sqlalchemy`, `fastapi`, `uvicorn`, `httpx` (the `server` extra) |

## Boundaries the import-linter contracts enforce

- `samplecore` has no dependents among its peers: nothing it does can accidentally couple to the
  extraction pipeline, the embedding pipeline, or the web server.
- `sampleserver` never imports `sampleextract`, `samplecloud` or `samplemorph`: the read API cannot trigger a
  batch job, and cannot inherit either pipeline's heavier dependencies.
- `sampleextract` is declared independent of both `samplecloud` and `samplemorph`: extraction
  never waits on embedding, and a change to either pipeline's dependencies never touches it.
- `samplemorph` never imports `samplecloud`, while `samplecloud` may import `samplemorph`: the
  cloud is the more general layer, and its `learned` backend loads a descriptor the morph pipeline
  trained. The import sits inside that backend's factory, so a pass over a hand-built descriptor
  keeps needing no torch. The morph pipeline still reaches the cloud through the catalog, writing
  a descriptor's vectors as `sample_feature_vector` rows under an `Experiment` that records the
  model's name, which is how the cloud's evaluation rebuilds the extractor and how a promotion
  finds the same vectors. This shape is provisional: if a model of the morph pipeline becomes the
  cloud's provider outright, the cloud turns into a layer over embedding providers, and the
  approach that passes the quality bar decides how the packages are reshaped.
- `samplemorph.service` reaches the pipeline alone: it never imports `samplemorph.training`,
  `samplemorph.commands` or any other package, and the shell and the service stay independent of
  each other, two skins over one pipeline. The web API reaches the service over HTTP, which is
  what keeps torch and the fitted models out of the API process while morphs play in the app.

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
The rate a sample's frames are really read at follows from that note *and* the occurrence's own
rate together (`rate * 2 ** ((sounded_note - 60) / 12)`, tracker C-5 being the rate's reference
key), which is why the two stay joined wherever they are counted: the same key struck against two
occurrences of one waveform sounds two speeds, and two different pairs meet at one speed -- a
waveform transposed down an octave and played an octave higher sounds exactly as the untransposed
one does. Both pieces of a tracker's own tuning are already in that rate: `trackmod` folds XM's
`relative_note`/`finetune` and MOD's finetune byte into the stored rate at parse time, and IT and
S3M carry the transposition in the keymap the sounded note comes from, so the pair is the whole
story. `samplecore.pitch` owns the rule and rounds an effective rate to whole hertz, tracker rates
being whole numbers and a fraction of a hertz sitting far below hearing.

A key reaching a sample below `minimum_sample_frames` keeps its note and
leaves its slot open, since the catalog holds no occurrence to name; a cell stating no instrument
leaves both open, its routing being a fact about how the song is played rather than what the cell
holds. `module_instrument` records each voice slot the same numbering addresses, and its names feed
`classify_sample_category` alongside the occurrence names -- a tracker names an instrument apart from
the waveforms its keys reach, so a sample stored as "smp03" is described only there.
`module_note_extraction` records which modules have been read, so a module whose patterns press no
keys still reads as finished and a resumed pass spares it a second parse.

`sample_playback_rate` holds the one rate each sample is heard at most often, which is what the
whole application plays a sample back at -- a click in the cloud, a listing thumbnail and the
waveform panel all sound the same sample identically because all three read this one number.
Answering it means folding tens of millions of note events against the occurrences they reach, some
fourteen seconds of work over this catalog, so `samplenotes` takes it once at the end of its own
pass and writes the whole answer down; a served request reads it per sample. A sample no pattern
plays has no row, and a reader falls back to `choose_dominant_rate` over its occurrences' own rates
-- what a module declares the waveform plays at, which is the closest reading left. Both rules break
a tie towards the lower rate, so a rate drawn from note events and one drawn from occurrence rates
are settled the same way.

A module every one of whose samples falls under `minimum_sample_frames` is ingested and kept like
any other, and stays reachable by its own hash and through `PostgresModuleRepository.list_all` for
the pipelines that walk every module. It is left out of `list_page`/`count`, so browsing passes over
it: a chiptune built from single-cycle waveforms is part of the collection while contributing
nothing to a library of samples. `LibraryStats` still counts every ingested module, that being a
statement about the catalog rather than about what is worth browsing.

## Hand-curated work

`curation.sample_annotation` holds what a person decided about a sample — what it is, as free text;
what they think of it, as a rating from one to five; and whether it belongs in their own collection —
and it is the one thing in this library no pass can rebuild. It therefore sits on a `MetaData` of its
own, in a Postgres schema of its own (`samplecore.storage.curation`), apart from the single
`MetaData` every other table belongs to. Both places this project empties a database —
`scripts/reset_library.py` and the test suite's own teardown — iterate
`database.metadata.sorted_tables`, so a table registered on the curation metadata is beyond their
reach by construction rather than by an exemption list somebody has to keep current. For the same
reason it carries no foreign key into the catalog: one would either delete these rows along with the
samples or block the purge outright. A test in `tests/scripts/test_reset_library.py` pins exactly
that, seeding an annotation and asserting it survives a full reset.

A label is stored in upper case, which is the case it is shown in: `LabelText` normalizes it at the
model boundary, so every path that records one — the curation route, a JSONL import, a relink —
agrees, and the vocabulary offered back gathers one entry per wording rather than one per way of
typing it.

What a label says is read by `samplecore.labeling`, and every consumer reads it the same way. A
label is a set of tags separated by commas, and each tag is a path whose colons step from a broad
category to a specification that means something only under it: `HI-HAT: CLOSED, LO-FI` names a
closed hi-hat that is also lo-fi. The whole path is a tag's identity, so `ELECTRIC` under `BASS`
and under `GUITAR` are two tags, and a path asserts every category above it. Two labels agree by
the overlap of those closed sets, from nothing shared to the same label, which gives graded credit
along the hierarchy -- a closed hi-hat beside an open one earns part of what a closed one would --
and reads a specification as a refinement of an agreement. Tags are attributes a sample carries
side by side, never classes it must pick one of, which is what lets a treatment such as `LO-FI` be
judged apart from a source such as `SNARE`. `sampleannotations vocabulary` lists the tags in use as
a tree with counts and names the wording worth a second look: a name standing both as a category
and as a specification under another, and tags carried by one sample. It reads and changes nothing;
settling the wording stays with the person, in the interface.

One row holds all three decisions, and exists because at least one of them was made — a CHECK
constraint says so, and `SampleAnnotation`'s own validator says so alongside it. Writes are
whole-state: `PUT /curation/annotations/{hash}` carries the complete state a sample should hold from
then on, so a decision left out is a decision undone, and a state recording nothing removes the row.
That makes one endpoint enough for setting, changing and clearing, and it is why
`replace_many` derives its column list from the table rather than keeping one by hand.

Because a sample's hash follows from how this project hashes audio, an annotation keyed on the hash
alone would be lost the moment that changes. Every annotation therefore also records the module slot
it was chosen from — module hash, filename, instrument index, sample slot, and the occurrence's name
(`samplecore.anchoring` owns that rule) — and `sampleannotations relink` reads those slots back to
recover whatever sample sits there now. The annotation is stored per sample even when it was applied
to a whole equivalence class at once, since a class is identified by a content hash over its members
and gains a different identity the moment its membership changes; `source` records which gesture
applied it, so a decision made about one sample stays distinguishable from one inherited from its
near-duplicates. A group member the catalog holds no occurrence for has nowhere to anchor, so the
gesture removes its annotation rather than leaving it saying what the group no longer says.

The samples listing reads these rows in its own query, joining `curation.sample_annotation` on the
sample hash, which is that table's primary key — so the join cannot fan out and `count` stays
consistent with the page it describes. `favorites_only` and `minimum_rating` therefore narrow the
whole catalog rather than one loaded window, which is what makes a collection scattered across a
hundred thousand samples browsable as a collection. Since every listing request now reaches that
schema, `create_app`'s startup prepares it once: the read-only connection every route uses can create
nothing, so a database the offline pipelines have never written to would otherwise fail to serve a
listing at all.

Every one of these decisions is made where a sample is met: the samples listing edits a category,
a rating and a favorite mark in the row itself, and the detail panel offers the same three. A
wording is recorded on Enter or on leaving the field, and emptying the field takes the hand label
back so the guessed category shows again -- one gesture to correct a wrong guess and one to undo it.
An edit reaches exactly what the row it was made in stands for: the whole equivalence class while
the listing groups near-duplicates together, and the one sample otherwise. `useAnnotationWriter` is
the single path all of them write through, so every row, badge and panel showing that sample follows
one write at once.

`sampleannotations export` writes every annotation to JSONL as the copy that outlives the database, and
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

## The three databases

One Postgres server carries three: the real library, `samplelibrary_dev` for the disposable
sandbox `scripts/build_dev_library.py` builds, and `samplelibrary_test` for the suite. One role,
named by `config.toml`'s `database_url`, owns all three.

`scripts/setup.py database` (`make database`) creates whatever of those is missing and touches
nothing that already exists, so it is safe against a populated library. `samplecore.storage.cluster`
owns that work: `quoting` turns a name or a password into a fragment of SQL and rejects what quoting
cannot carry (an empty identifier, or a NUL byte, which the driver would otherwise cut a name
short at), `statements` holds every statement this project runs against the cluster rather than
inside one database, and `provisioning` decides what to ask for. `CREATE ROLE` needs a superuser,
which `SAMPLELIBRARY_ADMIN_DATABASE_URL` supplies where the library's own credentials cannot;
without it the command reports the statement to run by hand.

Which database a run reaches is `database_url`, overridden by `SAMPLELIBRARY_DATABASE_URL` --
which is how the `*-dev` targets reach the sandbox, and how a deployment supplies credentials that
never live in a file. The suite reads `SAMPLELIBRARY_TEST_DATABASE_URL`, defaulting to
`samplelibrary_test` on localhost, and gives each `pytest -n` worker a database of its own, created
and dropped around the run: that is what the role's `CREATEDB` grant is for, and why
`samplelibrary_test` itself stays empty.

## Running extraction in parallel

`sampleextract --workers count` spends that many processes on one corpus, defaulting to one per
core up to `MAXIMUM_AUTOMATIC_WORKERS`. `sampleextract.parallel` owns the arrangement: the
supervisor walks the source directory once, `divide` splits the sorted discovery into one share per
worker by taking every `count`-th path -- striding rather than slicing into blocks, since paths
sorted by name group a directory's similar files together and contiguous blocks would hand one
worker all the large ones -- and each worker covers its share in a process of its own, opening its
own catalog connection. Progress crosses back on a queue so the supervisor draws one bar over the
whole corpus, and the workers' summaries fold into one through `ExtractionSummary.combine`.

Parsing is where the time goes, and it is ordinary Python, so shares want separate processes rather
than threads. Peak memory bounds how many: one module can materialize tens of thousands of note
events, and each worker carries that alone, which is what the ceiling on the automatic count is
for. The pool names `spawn` rather than taking the platform's default start method, so the promise
that no catalog connection is open when a worker starts holds wherever the run happens.

Four things make concurrent workers safe. `audio_store.write` stages its bytes in a temporary file
beside the destination and moves them into place in one step, so two workers reaching the same
sample hash -- routine, since one sample recurs across many modules -- each write a whole object
rather than interleaving into one. `create_schema` takes a Postgres advisory lock, so workers
opening the same fresh catalog at once create its tables in turn instead of racing on `CREATE TABLE
IF NOT EXISTS`. A module two workers reach at the same moment, which this corpus invites by holding
hundreds of byte-identical pairs under different names, is settled by the catalog's own uniqueness
on the module hash: the losing worker rolls its whole module back and counts it under
`ingested_elsewhere`.

And `ingest_module` writes the rows two workers can hold in common -- `sample` and
`sample_thumbnail`, both keyed by content hash -- in ascending hash order, ahead of the occurrences
keyed by `module_id` that belong to one worker alone. Ascending hash order is a total order every
worker agrees on, so two transactions holding one pair of samples between them reach those rows in
the same sequence and the second simply waits for the first. Taking them in the order a module's
own slots happen to list them would let two modules holding one pair in opposite orders each hold
what the other wants next, which Postgres resolves by aborting one with `DeadlockDetected` -- a
failure arriving as `OperationalError`, outside the `IntegrityError` a collision is read from, with
no retry anywhere in this project to fall back on.

## Deployment

Two packages run as long-lived services: `sampleserver`, the API, and `samplemorph.service`, the
morph inference process. `sampleextract` and `samplecloud` are one-shot offline batch scripts,
run by hand or on a schedule, never by the served app itself. The root `Dockerfile` builds a
runtime image for `sampleserver` alone, installing only the `server` extra (`fastapi`, `uvicorn`,
`httpx`) -- `sampleextract`/`samplecloud`'s own heavier dependencies (`librosa`, `umap-learn`,
`scikit-learn`) never reach that image, mirroring the `sampleserver never imports the offline
batch pipelines` import-linter contract above.

The inference process (`make serve-inference`) installs the `morph` extra, reads the library
root and the fitted models, and opens no database: a morph names two stored objects and a weight,
and the API, which knows the catalog, reads each sample's playback rate for the frontend the way it
does everywhere else. Both processes read one setting, `[inference] url` in `config.toml`: the
process binds it, the API dials it, and a morph request reaching the API while no process answers
comes back as 503 with that address in its detail. Renders are deterministic given the model
files, so each carries a validator built from the model's fingerprint and the point, and a browser
holding one is answered with a 304 by the process that made it.

Every route the API serves sits under `/api` (`sampleserver.app.API_PREFIX`), so one path always
names one thing: the frontend reaches `/api/samples` while a person's browser holds `/samples/{hash}`
as a client route of its own. That is what lets the Vite dev server forward a single prefix to the
backend and answer everything else with the application itself, so reloading a sample's own URL
brings back the dashboard.

`docker-compose.yml` adds a `postgres` service alongside it (a named volume for persistence), as a
worked example of the two running together; a real deployment points `database_url`/`SAMPLELIBRARY_DATABASE_URL` at
whatever Postgres instance it actually runs against, container or otherwise. Local development runs
against a Postgres installed on the machine directly, which the test suite and both library
databases share. The container runs multiple
`uvicorn` worker processes (`--workers`, not `--reload`) rather than the single-process dev server
`make serve` starts: each worker holds a small pool of read-only Postgres connections, checked out per request
(`sampleserver.dependencies.get_connection`), which Postgres's own concurrent-connection handling
supports natively, so multiple people browsing the library through one deployed server works
correctly with no shared state between workers. The library's data directory and a `config.toml`
pointing at its in-container path are supplied at `docker run` time (a bind mount plus
`SAMPLELIBRARY_CONFIG`), never baked into the image, mirroring `config.toml` never being committed
to the repository.

Three routes answer for the whole catalog at once — the cloud's hundred thousand points, a
nearest-neighbor search, the library statistics — and each is written for that shape rather than
scaled up from a per-sample one. A whole-catalog reader scans a table outright instead of naming
every hash it wants (`names_and_rates_for_every_sample` beside `names_and_rates_by_hash`), since a
hundred thousand bound parameters cost Postgres more than reading every row there is. The statistics
count and total in one grouped query rather than building a model per sample to sum. The spectral
vectors, which are stored as text and take a couple of seconds to parse, are held per application in
`SpectralVectorCache` and re-read only when the table's own revision moves, so a search costs one
cheap query rather than a fresh parse of the whole embedding.

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

### What the cloud costs

Measured on the real catalog of 127,588 samples over localhost on 2026-09-12, one uvicorn worker,
before and after each tier of the network work. The stages script
(`runs/cloud-2026-09-12/measure_stages.py` under the library root) times the server's own work
with no server running; `measure_routes.sh` beside it reads wire bytes and times off a running
`make serve`; the browser's parse time is `JSON.parse` over the fetched text in the console.

| Route or event | Before | After the trims | After the cache |
|---|---|---|---|
| `/api/cloud` wire bytes | 25.1 MB, plain | | |
| `/api/cloud` time to first byte | 2.7 s | | |
| `/api/cloud` server build | 2.7 s (reads 1.5, classification 0.66, models 0.55, serialization 0.23) | 2.1 s (reads 1.0, classification 0.48, models 0.45, serialization 0.17), once per revision after the cache | |
| `/api/cloud/suggestions` wire bytes and time | 26 MB, 4.0 s | | |
| `/api/cloud/suggestion-tags` time | 2.7 s | | |
| Cloud panel mount, category mode | 6 requests, 53 MB | | |
| Cloud panel reopen | 6 requests again | | |
| A hover | 2 requests, 2 connections, 120 ms | | |
| A replay of one sample | full download again | | |
| Browser parse of `/api/cloud` | 66 ms | | |

The trims: gzip on every response past a kilobyte; the audio route answering from the store with
an immutable cache lifetime and no catalog round trip; the suggestion tags counted in SQL; the
cloud's points without the hand label a viewer never read and with coordinates rounded to four
decimals; the module points without a timestamp each; the suggestions as each sample's first pick
alone; a hover served by one preview route reading the stored thumbnail; the points cached for
the session in the browser and the label and suggestion sources fetched only in the mode that
paints by them. Measured on the same body, gzip alone takes the cloud's response to 9 MB and the
trims together to 6.7 MB; a binary columnar layout would reach 5.2 MB, most of it the hashes, and
is worth its own format only if the gzipped body passes 10 MB or the download and parse pass a
second on a real link.

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
were until that deliberate step. `samplecloud --backend <name> --extract-only` runs the extraction
alone, for an experiment made to be measured or to teach another descriptor; running the same
experiment again by its id, without the flag, promotes it.

The `clap` backend reads a pretrained audio-text model (`samplecloud.backends.teacher_backend`,
behind the `teacher` extra), which knows sound from what people wrote about recordings and, on the
first hand labels, leads both hand-built descriptors by a wide margin. It computes the model's own
log-mel picture on the device, at a quarter of the library extractor's cost. Beside its place in
the cloud it is the teacher the `samplemorph` descriptor is distilled from, which is where its one
weakness -- it moves under an octave's retuning -- is repaired.

Every pass reads a sample one of two ways (`samplecloud.hearing`), recorded in the experiment's
parameters as `reading`: at the nominal rate the store writes, the reading every cloud is built
on, or, with `--heard-rate`, at the rate the library plays the sample at, resampled through
`samplecore.waveform.heard_at_rate` so a bass played two octaves below its file's rate reaches the
extractor as a bass. The heard-rate reading is what naming an instrument needs, since the
listening model's rate invariance ends within a whole tone.

`samplecloud-suggest` turns a `clap` experiment's vectors into labels. The text tower reads a
vocabulary of prompts in the hand-label grammar -- the shipped instrument list, the tags people
wrote, or a file with one label per line -- into the same space, one cosine per sample and label
ranks them, and each sample keeps its closest few under a new experiment of the `zero_shot`
backend, whose parameters name the source experiment, the checkpoint, the prompt template and the
vocabulary in order (`sample_label_suggestion`, `samplecore.storage.repositories.label_suggestion`).
The command reports how the first picks spread over the vocabulary and how they agree with the hand
labels, exactly and by category. Suggestions are rebuildable, so they live in the main schema beside
the feature vectors; the newest scoring is the one the application shows.

### Judging a descriptor

`samplecloud.evaluation` scores any experiment's vectors against four targets the catalog already
carries, so a change to an extractor is answered by numbers rather than by an impression.

- **Transposition retrieval** retunes a sample by a fixed mirrored grid of semitone offsets,
  describes the result, and reports where the original ranks against the whole catalog. It needs no
  label at all, since retuning produces a query the catalog holds the answer to. Rank-1 and rank-5
  shares travel beside the median rank, because a descriptor placing the original second every time
  and one placing it forty-thousandth both score zero at rank one.
- **Category agreement** classifies each keyword-labeled sample from its neighbors. `UNCATEGORIZED`
  stays out, since it records that no keyword matched rather than a class the samples share, and
  macro-F1 sits beside accuracy because supports run from about a hundred to a few thousand.
- **Note-event agreement** predicts how many distinct pitches a sample is played at and how wide a
  span it covers, scored by rank correlation. Both are continuous, because the percussive and tonal
  split they were once read as is a tendency rather than a division. A second reading covers only
  samples struck often enough for a pitch count to mean something, since a sample struck twice shows
  at most two pitches whatever it is.
- **Hand-label agreement** ranks every labeled sample's labeled neighbors and credits each by how
  much its label agrees with the query's, graded along the hierarchy as `samplecore.labeling`
  defines it. NDCG over the nearest ten reads the whole neighborhood, precision at one asks whether
  the nearest shares any tag, and every tag with enough support is scored on its own by average
  precision. The labeled set is small and grows as the person labels, so the NDCG carries a
  bootstrap interval over the queries and every score its chance level. A label depth reads the
  labels to that many levels, for a coarser reading of the same set.

Each metric reports the share of the catalog it describes, so a reader sees which part of the
library a score speaks for. Splits are grouped by equivalence class, which changes nothing while
`sample_relation` is empty and becomes correct on its own once it is not. One seed fixes every split
and every draw, so a second run reproduces every number. `samplecloud-evaluate` records each pass
as a run in the tracking store beside the library (`samplecore.tracking`), one metric per
question under its own namespace and the whole report as an artifact, so two descriptors are
compared from the store rather than from two terminals; `--no-tracking` keeps a quick look out of
it. The harness itself returns the report and writes nothing, and `samplecloud.evaluation.recording`
is the one place that reads the report into a run.

This lives in `samplecloud` rather than `samplemorph` because it judges embeddings, which is what
`samplecloud` owns. A learned codec's latents reach it as an ordinary experiment through the
database, with no import in either direction, which is what keeps the two pipelines independent.

A descriptor of this kind answers what a sample resembles. Producing audio from a point between two
samples asks for a representation carrying a decoder as well, which is a separate design: the
research behind it, the measured facts about the corpus it rests on, and the staged plan for the
`samplemorph` package live under [`morphing/`](morphing/00-handover.md).

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
many to stay reliably distinguishable by hue alone for every viewer. In the badge a hand label
wears one style of its own, being free text.

The cloud can also color by the hand labels' own tags, with nothing about any tag known to the
frontend. `GET /curation/annotations/tags` reads the tag tree out of the labels through
`samplecore.labeling`, each tag with its count and a rank by the order it was first used, and
`GET /cloud/labels` carries every labeled sample's tags in the order the person wrote them, apart
from the points because a few hundred labels change with every label written while a hundred
thousand points change only with the embedding. The frontend paints a tag in a color that is a
function of its rank alone (`labelPalette.ts`: hues a golden angle apart, at the lightness and
chroma each theme declares), so a tag keeps its color as the vocabulary grows and a new one takes
the next hue; the legend is the picker, painting the most used top-level tags until a person
chooses their own, listing the painted ones with the rest behind a toggle inside a strip of at
most three rows, and a sample carrying several painted tags takes the first it was given
(`labelColoring.ts`). Everything a painted tag does not reach stays on the recessive tone the
uncategorized points use.

A third kind of label travels beside the two: what the listening model hears a sample as, the
suggestions a `zero_shot` scoring wrote. `GET /cloud/suggestions` carries each sample's first
suggested tag path with its score, apart from the points like the hand labels, and
`GET /cloud/suggestion-tags` the tags suggested first with their counts, each counting toward its
category and ranked by its place in the scoring's vocabulary, so the same legend and palette paint
the cloud by suggestion. A sample's detail carries `suggested_labels`, and `SuggestedLabels` shows
each as a dashed badge with its score: a click appends the tag to the hand label through
`useAnnotationWriter`, the one write path every annotation gesture takes, reaching the sample's
near-duplicates the way the editor's own default does, and a tag the label already holds shows as
taken. The suggestion stays a suggestion until a person accepts it: the hand label wins wherever
one exists, and the badge that names a sample never shows a suggestion.

## Morphs in the application

A morph is a pair of samples and a weight between them, held in `frontend/src/morph/morphStore.ts`
apart from the shell's focus and comparison slots: comparing two samples and morphing between two
are different acts, and clearing one leaves the other. The cloud fills the pair with the right
mouse button, which regl-scatterplot leaves alone (it pans and selects on the left button only), so
the browser's menu is the one thing `CloudView` keeps off the canvas: a right-drag from one point to
another joins the two, and a right-click on a point joins it to the highlighted or focused sample.
While the button is held, a band runs from the point the drag started at, or from that sample when
the press landed on empty space, to the cursor, snapping to the point under it
(`frontend/src/cloud/MorphBand.tsx`), so the pair a release would join is visible before it lands;
the join then draws a dashed line between the two with a marker that is the weight
(`frontend/src/cloud/MorphLink.tsx`), pinned through pan and zoom the way the ping is. The Morph
panel mirrors the same weight as a slider, names both ends with the
link every listing row carries (a click highlights the end, a double-click opens it in the Sample
Detail), and plays the render on release through the one preview element every sample plays
through (`useAudioPreview`, whose sources carry a URL and a key, so a morph is keyed by its own
render's address). Both ends are carried into one frame before they blend: the API resolves the
rate each is heard at by the one rule every reader of the catalog applies and hands both to the
inference process, which resamples the slower sample up to the faster one's rate, the higher of
the two, so the faster keeps its whole band and the slower loses nothing, and states that rate in
the file it answers with. The frontend plays a morph as the file says, so a path between two
samples an octave apart in rate holds each end at its own pitch and sounds every point between
at the one rate, where a blend in the stored frame played at a rate sliding between the two would
carry both ends' pitches through the gap. Weights lie on a grid of sixteenths on both sides, so a
weight names one render and one cache entry wherever it goes.

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
