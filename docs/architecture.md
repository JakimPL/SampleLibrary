# Architecture & Ownership

SampleLibrary turns a personal collection of tracker modules, and folders of plain audio files
beside it, into a browsable, deduplicated sample library: a Postgres catalog of modules, samples,
their tracker-specific properties and the sample files they were found in; a content-addressable
store of extracted audio; detected equivalence classes between near-duplicate samples; and a web
application for navigating and visualizing all of it. The project has two
natures — an offline, batch-oriented extraction/analysis tool, and a served read-only web app —
kept as six packages under one `pyproject.toml` so each keeps its own dependency footprint and
its own write/read boundary, enforced by the `[tool.importlinter]` contracts in `pyproject.toml`.

## Package map (`src/`)

| Package | Owns | Depends on |
|---|---|---|
| `samplecore` | The domain models (`Module`, `Sample`, `SampleProperties` and its tracker-specific subtypes, `SampleRelation`, `Experiment`, `SampleFeatureVector`, `EquivalenceClass`, `SampleSpectralFeature`, `NoteEvent`, `ModuleInstrument`, `SampleAnnotation`), the reading of a hand label as tag paths and the agreement between two of them (`samplecore.labeling`), the Postgres schema and connection helpers, the content-addressable audio store, sample hashing, equivalence-class grouping, spectral-distance computation, the pitch rule that turns an occurrence rate and a pressed key into the one rate a sample is really played at, the anchoring rule that keeps a hand label attached to its sample, the sample files read in place from configured sample directories (`samplecore.sample_files` decodes one into the sample it holds, and `samplecore.storage.sample_audio.SampleAudio` is the one reader of every sample's audio, from the store or from its files), the waveform hygiene every analysis shares (folding to mono, the subsonic high-pass), the auditory front end (`samplecore.auditory`: an ERB-spaced gammatone bank, subband envelopes and the two-lobe modulation spectrum a listener hears flutter and roughness on, designed once as data so a numpy reading and a torch loss apply the same kernels), and the local `LibraryConfig` loader. A leaf: nothing else in this repository. | `psycopg`, `sqlalchemy`, `numpy`, `scipy`, `pydantic`, `soundfile` |
| `sampleextract` | The offline extraction pipeline: walking the module source directory, parsing modules via `trackmod`, rendering sample audio to the content store, populating the Postgres catalog, scanning the configured sample directories into the catalog in place (`sampleextract.files`, the `samplelibrary files` command), spreading either pass over worker processes (`sampleextract.parallel`), computing cached waveform-preview thumbnails, reading each module's patterns for the notes they play (both inline at ingest, and via a standalone backfill pass each) and folding those notes into the rate each sample is heard at, the equivalence-class detection pass, and moving hand labels in and out of the catalog. | `samplecore`, `sqlalchemy`, `trackmod`, `tqdm` |
| `samplecloud` | The offline embedding pipeline for the sample-cloud visualization: pluggable feature extraction (`FeatureExtractor` protocol) scoped to a named `Experiment` so more than one backend or parameter set can extract concurrently without clobbering another's vectors -- two hand-built descriptors, and a pretrained audio-text model behind the `clap` backend (the `teacher` extra) that hears what people would call alike, teaches the descriptor `samplemorph` trains, and through its text tower suggests labels for every sample from a vocabulary of prompts (`samplecloud.suggestions`, each scoring an `Experiment` of its own), UMAP dimensionality reduction (explicit Euclidean metric) over one chosen experiment, and persistence of each sample's standardized vector and 2D coordinate -- the standardized vector is `samplecore`'s own named spectral-distance metric, reused by `sampleserver`'s distance endpoints. It also owns the evaluation harness (`samplecloud.evaluation`) that scores any experiment's descriptor against the targets the catalog already carries: whether a retuning moves the descriptor, whether it groups what the note events say the library plays alike, and whether it groups what a person labeled alike. Depends on `samplecore`, and on `samplemorph` inside its `learned` backend's factory, never on `sampleextract`, so a future heavy embedding backend's dependencies never reach the extraction pipeline or the web server. | `samplecore`, `samplemorph` (the `learned` backend), `sqlalchemy`, `librosa`, `umap-learn`, `scikit-learn`, `mlflow` (the `cloud` extra); `torch`, `transformers` (the `teacher` extra) |
| `samplemorph` | The decodable-representation pipeline: canonicalizing a sample into a fixed-size sound image on a log-frequency by duration-fraction grid together with the three conditioners that image was normalized by (where its content sits in pitch, how long it sounds, and how loud it was), and a pluggable `Vocoder` turning a magnitude spectrogram back into audible frames -- in production a restorer taught what the grid's band averaging removes from this library's own sounds, followed by phase gradient heap integration under a Gaussian analysis -- and a learned `Descriptor` (`samplemorph.descriptors`) that reads the canonical grid as one vector: distilled from the pretrained listening model, taught by retuned views that a retuning changes nothing, and by the hand labels what the listener calls alike. A conditioned codec (`samplemorph.codecs.conditioned`) decodes the grid from that descriptor beside a small residual under a prior, so a morph moves a sound's identity through the space the harness judges and its particulars through a space where every point decodes. The frequency axis is logarithmic, which turns a change of playback rate into a translation along it, so the translation is measured, moved out of the grid, and carried as a conditioner -- which is what leaves the representation invertible where the sample cloud's descriptors are not. Training passes (`samplemorph.training`) run under a run tracker and read a grid cache canonicalized once under the library root. A training-free spectral transport (`samplemorph.transport`) morphs two sounds' own analyses by carrying their partials, bands and envelopes along paths of their own; over it, `samplemorph.partials` reads a sound as notes and harmonic channels over a residual, sounds the channels as oscillators along the paths a `MorphProfile` names and transports the residual, which holds a chord's voices steady where the transport alone warbles. One priced assignment settles which channel travels to which and which fades where it stands, read once for a pair of sounds, so a partial glides one path from end to end. `samplemorph.routes` puts all of them, the decibel crossfade control and the latent route behind one protocol, which the listening comparison (`samplemorph.listening`, run by `morph draw-pairs` and `morph compare`) renders side by side with readings of every path. Each shell command is one module under `samplemorph.commands`, and the ones that train import the trainer only when they run, so parsing arguments and the commands that train nothing stay clear of it. `samplemorph.service` is the same pipeline over HTTP: the morph inference process (`samplelibrary morph serve`), which loads the fitted models once, renders any point between two cataloged samples on request, reading a sample found in a sample directory from the file the request names inside the directories its own configuration lists, and is what the web API dials for a morph. Depends on `samplecore` only. | `samplecore`, `librosa`, `scikit-learn`, `torch`, `fastapi`, `uvicorn` (the `morph` extra) |
| `sampleserver` | The FastAPI API serving the catalog, cross-references, equivalence classes, spectral distances, stats, and cloud coordinates to the frontend, plus the curation routes recording a person's own decisions about samples, and the morph routes, which relay renders from the inference process over HTTP. Every route is served under `API_PREFIX` (`/api`), which keeps the whole API inside one path segment and leaves every other path to the single-page application's own routes. Every catalog read opens its Postgres connection read-only, so a bug in a route handler cannot corrupt the library; the curation routes hold the one writable connection, and it reaches only the `curation` schema's own tables. | `samplecore`, `sqlalchemy`, `fastapi`, `uvicorn`, `httpx` (the `server` extra) |
| `samplelibrary` | The `samplelibrary` command line: one parser naming every operation on the library, which hands the rest of a command line to the module owning that command and imports that module as the command runs, so listing the commands stays instant and each command needs its own package's extras alone. A global `--config` sets `SAMPLELIBRARY_CONFIG` and drops any exported `SAMPLELIBRARY_DATABASE_URL`, so the file it names supplies the database too, and every process a command starts inherits both -- uvicorn's workers and a pipeline's worker processes included. The dispatcher accepts a command's own arguments only after its name. It also holds the commands that belong to no pipeline: `setup` (the config file and the databases), `reset`, and `tracking uri` / `tracking ui`, and the sandbox's synthetic modules and sample pack (`samplelibrary.sandbox`). Every command ends with one of the statuses `samplecore.exit_status.ExitStatus` names: 0 once its work is committed, per-item failures included as warnings, 1 when something broke, 2 for a malformed command line, 3 for a request it refuses, and 4 for a process that outgrew its memory ceiling. `--memory-cap 16G` holds the command and everything it starts to a memory ceiling before it loads anything of its own (`samplelibrary.limits`): on Linux the process starts again inside a systemd user scope with swap closed off and reads the ceiling back from its own control group, on Windows it assigns itself to a job object of that name, and a system offering neither refuses a ceiling rather than running uncapped. `--memory-scope` names the scope, which is what another process finds a running step by. When `SAMPLELIBRARY_STEP_LOCK` names a lock, the dispatcher holds that Postgres advisory lock for the life of the command, which is how a pipeline recognizes a step still running. It sits over every other package. | every package above |

## Boundaries the import-linter contracts enforce

- `samplecore` has no dependents among its peers: nothing it does can accidentally couple to the
  extraction pipeline, the embedding pipeline, or the web server.
- `sampleserver` never imports `sampleextract`, `samplecloud` or `samplemorph`: the read API cannot trigger a
  batch job, and cannot inherit either pipeline's heavier dependencies. The pipelines never import
  `sampleserver` either: they write the catalog the server reads, and meet it there alone.
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
- `samplelibrary` sits over every package, and none of them imports it. Each command keeps its
  parser and its `main(argv, prog=...)` in the package that owns the work, so a test runs a command
  the way a shell does.

## Persistence

Postgres is the single authoritative store for all catalog metadata (`Module`, `Sample`,
`SampleProperties` together with its per-tracker `xm_sample_properties`/`it_sample_properties`/
`s3m_sample_properties` tables (MOD carries no properties beyond the shared base, so it has no
table of its own), `sample_file`, `SampleRelation`, `Experiment`, `sample_feature_vector`,
`sample_cloud_coordinates`, `module_cloud_coordinates`, `sample_spectral_feature`,
`sample_thumbnail`, `module_instrument`, `note_event`, `module_note_extraction`, `sample_playback_rate`,
`sample_label_suggestion`, and `cloud_promotion`). Equivalence classes are not a stored table: `samplecore.equivalence_classes`
derives them on request from `SampleRelation` rows, since the relation graph stays small even at
real-catalog scale. The filesystem content-addressable store —
`{library_root}/objects/{hash[0:2]}/{hash}.wav`, one file per unique `Sample` extracted from a
module — is the authoritative store for extracted audio bytes, and a sample found only in a sample
directory keeps its bytes in its own file (see [Samples read in place](#samples-read-in-place)).
Neither is a cache of the other, except that `Sample` rows could in principle be rebuilt by
rehashing the store and the sample directories; that is a recoverability property, not a substitute
for backing up the catalog itself.

`sample_feature_vector` holds one `FeatureExtractor` backend's raw output per sample, scoped to an
`Experiment` row (its backend name, parameters, and a human label) rather than a single global
table: two experiments extracting concurrently write disjoint rows, keyed by
`(experiment_id, sample_hash)`, so neither can clobber the other's vectors. `sample_cloud_coordinates`,
`module_cloud_coordinates`, and `sample_spectral_feature` stay singular and global -- they represent
whichever experiment has been deliberately *promoted* (`samplecloud.reduce.reduce_and_persist_coordinates`,
given an explicit `experiment_id`), not per-experiment scratch space. `cloud_promotion` holds one row
naming that experiment, written in the same transaction as the coordinates, which is how a later
pass knows which experiment the cloud shows: `samplelibrary cloud embed --resume-promoted` resumes
it rather than opening a new one, and the pipeline's `cloud` step is satisfied once it names the
learned experiment.

Stored objects are written through `samplecore.storage.atomic.write_atomically`: staged beside the
destination, flushed, and moved into place whole, ending with the permissions a plain file gets
under the writing process's umask, so a library one user extracts is readable by a container
running as another. A library written before objects were made readable wants
`chmod -R a+rX objects` under its root once.

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
holds. `module_instrument` records each voice slot the same numbering addresses, with the name its
author gave the voice -- a tracker names an instrument apart from the waveforms its keys reach.
`module_note_extraction` records which modules have been read, so a module whose patterns press no
keys still reads as finished and a resumed pass spares it a second parse.

`sample_playback_rate` holds the one rate each sample is heard at most often, which is what the
whole application plays a sample back at -- a click in the cloud, a listing thumbnail and the
waveform panel all sound the same sample identically because all three read this one number.
Answering it means folding tens of millions of note events against the occurrences they reach, some
fourteen seconds of work over this catalog, so `samplelibrary notes` takes it once at the end of its
own pass and writes the whole answer down; a served request reads it per sample. A sample no pattern
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
`samplelibrary reset` and the test suite's own teardown — iterate
`database.metadata.sorted_tables` (`samplecore.storage.reset` owns the first), so a table registered on the curation metadata is beyond their
reach by construction rather than by an exemption list somebody has to keep current. For the same
reason it carries no foreign key into the catalog: one would either delete these rows along with the
samples or block the purge outright. A test in `tests/samplecore/storage/test_reset.py` pins exactly
that, seeding an annotation and asserting it survives a full reset.

A label is stored in one canonical spelling, `HI-HAT: CLOSED, LO-FI` — upper case, one space after
each colon and comma, each tag path once, in the order written — which is the spelling it is shown in:
`LabelText` applies `samplecore.labeling.labels.canonical_label` at the model boundary, so every path
that records one — the curation route, a JSONL import, a relink — agrees, and the vocabulary offered
back gathers one entry per wording rather than one per way of typing it.

What a label says is read by `samplecore.labeling`, and every consumer reads it the same way. A
label is a set of tags separated by commas, and each tag is a path whose colons step from a broad
category to a specification that means something only under it: `HI-HAT: CLOSED, LO-FI` names a
closed hi-hat that is also lo-fi. The whole path is a tag's identity, so `ELECTRIC` under `BASS`
and under `GUITAR` are two tags, and a path asserts every category above it. Two labels agree by
the overlap of those closed sets, from nothing shared to the same label, which gives graded credit
along the hierarchy -- a closed hi-hat beside an open one earns part of what a closed one would --
and reads a specification as a refinement of an agreement. Tags are attributes a sample carries
side by side, never classes it must pick one of, which is what lets a treatment such as `LO-FI` be
judged apart from a source such as `SNARE`. `samplelibrary annotations vocabulary` lists the tags in
use as a tree with counts and names the wording worth a second look: a name standing both as a
category and as a specification under another, and tags carried by one sample. It reads and changes
nothing; settling the wording stays with the person, in the interface.

One row holds all three decisions, and exists because at least one of them was made — a CHECK
constraint says so, and `SampleAnnotation`'s own validator says so alongside it. Writes carry only
what changed: `PATCH /curation/annotations/{hash}` names a scope and any of `label`, `rating` and
`favorite`, a field left out stays as it is and `null` clears it, so two gestures on one sample — a
label typed while a star is clicked — both land. The route merges the change into each reached
sample's row under a transaction-scoped advisory lock (`samplecore.storage.annotation_writes`), leaves
a member the change does not alter untouched, and removes a row left recording nothing; the answer
lists each sample written with what it holds now, and the members it skipped for want of an anchor.
`DELETE /curation/annotations/{hash}` removes one annotation outright, including one for a sample
the catalog no longer holds. In the app, `annotationWriteQueue` sends one sample's changes in order,
and `annotationStore` shows a change at once and reverts it when the write fails.

`curation.tag_rank` gives every tag path a rank that never moves once given: seeded once from the
labels in the order they were first used, and extended inside the write that first uses a new tag.
The cloud paints a tag by its rank, so a rating written on an old label leaves every color where it
was.

Because a sample's hash follows from how this project hashes audio, an annotation keyed on the hash
alone would be lost the moment that changes. Every annotation therefore also records an anchor
(`samplecore.anchoring` owns that rule): the module slot it was chosen from — module hash, filename,
instrument index, sample slot, and the occurrence's name — or, for a sample found only in sample
directories, the sample file it was chosen from. `SampleAnnotation.anchor` is the union of the two,
told apart by `kind` in the JSONL a transfer writes, and the table keeps both anchors' columns with a
CHECK holding each row to exactly one of them. `samplelibrary annotations relink` reads each anchor
back to recover whatever sample sits there now. The annotation is stored per sample even when it was
applied to a whole equivalence class at once, since a class is identified by a content hash over its
members and gains a different identity the moment its membership changes; `source` records which
gesture applied it, so a decision made about one sample stays distinguishable from one inherited
from its near-duplicates. A group member the catalog holds neither an occurrence nor a file of has nowhere to anchor,
so the gesture removes its annotation rather than leaving it saying what the group no longer says.

The samples listing reads these rows in its own query, joining `curation.sample_annotation` on the
sample hash, which is that table's primary key — so the join cannot fan out and `count` stays
consistent with the page it describes. `favorites_only` and `minimum_rating` therefore narrow the
whole catalog rather than one loaded window, which is what makes a collection scattered across a
hundred thousand samples browsable as a collection. Since every listing request now reaches that
schema, `create_app`'s startup prepares it once: the read-only connection every route uses can create
nothing, so a database the offline pipelines have never written to would otherwise fail to serve a
listing at all.

Every one of these decisions is made where a sample is met: the samples listing edits the label
behind a sample's category, a rating and a favorite mark in the row itself, and the detail panel
offers the same three. A wording is recorded on Enter or on leaving the field, and emptying the
field takes the hand label back so what the listening model heard shows again -- one gesture to
correct a wrong suggestion and one to undo it.
An edit reaches exactly what the row it was made in stands for: the whole equivalence class while
the listing groups near-duplicates together, and the one sample otherwise. `useAnnotationWriter` is
the single path all of them write through, so every row, badge and panel showing that sample follows
one write at once.

`samplelibrary annotations export` writes every annotation to JSONL as the copy that outlives the
database, and `import` merges a file back without clearing anything, in one transaction under the
same lock; a file naming one sample on two lines is refused whole, naming the lines. `relink` leaves
an annotation alone when the sample now in its slot carries a decision of its own, and names it.
Every import records the file it read in `curation.annotation_import`, named by the SHA-256 of its
bytes with the count it held, in the transaction that lands the annotations, so whether a library
already took in a given file is one lookup, wherever that file sits now.

Local, machine-specific configuration (the module source directory, the library root, the catalog's
connection URL) is read from a gitignored `config.toml` via `samplecore.config.load_config`, never
hardcoded into source; the connection URL can also be supplied via the `SAMPLELIBRARY_DATABASE_URL`
environment variable (taking precedence over the config file), so credentials need not live in a
file at all. A command given `--config` reads the database from that file alone. `config.example.toml`
documents the expected shape.

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
sandbox, and `samplelibrary_test` for the suite. `scripts/build_dev_library.py` builds the sandbox from
`samplelibrary.sandbox`, which the suite reads the same modules and sample pack from,
together with a config naming `samplelibrary_dev` on the server, role and password of the configured
library (`provisioning.development_database_url`), and an inference address of its own, so the
sandbox's API never dials the real library's renderer. One role, named by `config.toml`'s `database_url`, owns all
three.

`samplelibrary setup database` (`just database`) creates whichever of the role and the databases
are missing and adds any missing tables to the library and the sandbox, leaving every row in place,
so it is safe against a populated library. `samplecore.storage.cluster`
owns that work: `quoting` turns a name or a password into a fragment of SQL and rejects what quoting
cannot carry (an empty identifier, or a NUL byte, which the driver would otherwise cut a name
short at), `statements` holds every statement this project runs against the cluster rather than
inside one database, and `provisioning` decides what to ask for. `CREATE ROLE` needs a superuser,
which `SAMPLELIBRARY_ADMIN_DATABASE_URL` supplies where the library's own credentials cannot;
without it the command reports the statement to run by hand.

Which database a run reaches is `database_url`, overridden by `SAMPLELIBRARY_DATABASE_URL`, which
is how a deployment supplies credentials that never live in a file. `--config` wins over both: the
`dev` recipes pass the sandbox's config, and the file's database is the one they reach whatever the
environment holds. The suite reads `SAMPLELIBRARY_TEST_DATABASE_URL`, then the server the
configuration names under the `samplelibrary_test` database, then `samplelibrary_test` on localhost,
and gives each `pytest -n` worker a database of its own, created and dropped around the run: that is
what the role's `CREATEDB` grant is for, and why `samplelibrary_test` itself stays empty.

## Samples read in place

`sample_directories` in `config.toml` names folders of plain audio files, and
`samplelibrary files` catalogs every WAV, AIFF and FLAC file inside them without copying a byte:
`sample_file` holds one row per file, keyed by the configured directory and the file's forward-slash
path inside it, naming the sample the file decodes to, the rate the file declares, and the file's
size and write time. `sample_exclusions` lists shell patterns matched without regard to case against
each path relative to its directory, and an excluded folder is left unwalked; dot-prefixed names,
such as the resource forks macOS leaves beside a file, stay out as well. The directories are
absolute and stand apart from one another, so a file has exactly one row.

A file decodes into the catalog's own form (`samplecore.sample_files.decoding`): 8-bit files stay 8
bits and every deeper or floating-point encoding is quantized to 16, mono and stereo alike, and the
hash is `compute_sample_hash` over those quantized frames, so a file byte-identical to a module's
sample lands on the same `sample` row. The formats read are lossless, which gives one file one hash
for as long as its bytes stay the same. A scan writes the sample, its thumbnail and the file row in
one transaction, in the order every scan takes them, and passes over a file whose size and write time
match its row without reading it, so a repeat scan costs a status call and a lookup per file.

The audio of such a sample lives only in its file, which can be deleted, rewritten or on a drive
that is no longer mounted. `SampleAudio` is the reader every pass and the API share: a sample with a
stored object is read from the store, and otherwise from the first of its files in location order
whose size and write time still match and which still decodes to the sample's hash. A sample none of
whose files qualifies raises `SampleUnavailableError`, which each pass catches around the read alone
and counts: thumbnails, equivalence detection (at fingerprinting, and for a pair whose file vanishes
while the pass runs), feature extraction (the sample stays pending), transposition probes, the
reproducibility probe of a resumed experiment (which compares the first samples it can read), and
the morph training sets. A fit, a grid cache or a training run sized to its samples first keeps the
samples `readable_samples` finds, and a file vanishing mid-build stops that build with the previous
cache left in place. A missing stored object is a damaged store and still raises
`FileNotFoundError`. The API serves such a sample's audio as the WAV the store would hold for it,
with the same nominal header rate and the same year-long cache lifetime, and answers 404 naming the
file when none can be read; the sample detail lists its files, each with whether it is available now.

Names and rates read files beside occurrences. A file's name without its suffix counts among the
names the waveform is stored under, which the display name is drawn from; and its declared rate
joins the occurrence rates a sample with no note events is played at, which the frontend applies to
the nominal header the way it does for every sample.

## Running extraction in parallel

`samplelibrary extract --workers count` spends that many processes on one corpus, defaulting to one
per core up to `MAXIMUM_AUTOMATIC_WORKERS`, and `samplelibrary files --workers count` does the same
for the sample directories. `sampleextract.parallel` owns the arrangement for both: the caller walks
the collection once and hands the supervisor the work list, the pass one share runs and the way
summaries combine; `divide` splits the sorted discovery into one share per worker by taking every
`count`-th item -- striding rather than slicing into blocks, since paths sorted by name group a
directory's similar files together and contiguous blocks would hand one worker all the large ones --
and each worker covers its share in a process of its own, opening its own catalog connection.
Progress crosses back on a queue so the supervisor draws one bar over the whole work list, and the
workers' summaries fold into one through `ExtractionSummary.combine` or
`SampleFileScanSummary.combine`.

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

## Removing what the collection no longer holds

Extraction adds and never removes, so a module deleted from the collection stays cataloged until
`samplelibrary extract --prune` removes it. The pass decides what is gone from what the run itself
read (`sampleextract.prune`): every module file it opened, those it failed to parse included, stays.
It refuses whenever that reading could be incomplete — a worker failed, a file or a folder could not
be read, or the collection yielded no file while modules are cataloged, as an unmounted drive does —
and while another extraction, scan or notes pass holds the extraction lock in shared mode.
`samplecore.storage.prune` then deletes, in one transaction, every row naming a gone module and every
sample neither a module occurrence nor a sample file holds (`SAMPLE_HOLDER_TABLES`), with each table
reaching either, and afterwards unlinks those samples' objects and sweeps any object the catalog does
not name.

`samplelibrary files --prune` does the same for sample files (`sampleextract.files.prune`). A file is
gone when the scan found it nowhere: deleted, named by an exclusion now, or under a directory the
configuration no longer lists, since the configuration declares the collection. The prune refuses
on the same incomplete readings, on a configured directory that is missing, and on a configured
directory that yielded no file while files under it are cataloged, which is what the empty mount
point of an unplugged drive looks like. Hand annotations stay;
`annotations relink` reattaches the ones whose slot now holds another sample.

## Detecting near-duplicates

`samplelibrary equivalence` finds pairs of samples that are one sound stored twice: at another bit
depth, at another level, or read at another rate. It streams the catalog once, trimming each
waveform's trailing silence and reducing it to two short fingerprints (`sampleextract.equivalence.fingerprint`):
one over bands relative to the waveform's own length, which a change of depth or level leaves alone,
and one over cycle-count octave bands, which a resampling leaves alone. A blockwise dot product
finds each fingerprint's close neighbors (`candidates.py`), the shape fingerprint proposing gain
pairs of nearly equal trimmed length and the rate fingerprint proposing resampled pairs further
apart, and only those pairs are read again and scored on the waveforms themselves (`scoring.py`),
through a cache that keeps the most recently read waveforms. Each block of pairs is scored and written in its own
transaction, so an interrupted run keeps the blocks it finished and a rerun writes the same rows.
Silent samples take no part.

`pass_completion` holds one row per kind of whole-library pass that finished completely, naming a
digest of what it had in front of it (`samplecore.digests`), so a pass finding the same digest again
ends with nothing to do. `extract --prune` records a digest of every module file's path, size and
write time once its prune succeeded and a second listing finds the collection unchanged, since only a
pruned pass leaves a catalog mirroring the collection; `notes` records the cataloged modules it read
every file of; `equivalence` records the samples that can be read as far as a status call tells
(`readable_sample_hashes`: every sample a module holds, and every sample file standing with its
scanned size and write time), taken before and after its pass, unless the two differ or the pass was
limited to a slice. A pass that goes ahead drops its record first, so an interrupted pass leaves none,
and `--force` goes ahead whatever the record says. The records live in the catalog, so a reset forgets
them along with the rows they describe.

## Building the library in one command

`samplelibrary pipeline run [TARGET…]` (`samplelibrary.pipeline`) builds the library through its
steps, one at a time and each in a process of its own: the catalog passes (`labels`, `modules`,
`sample-files`, `notes`, `thumbnails`, `equivalence`, `relink`), the listening model's two readings
and its suggestions (`teacher`, `hearing-teacher`, `suggestions`), the descriptor from its grid cache
to the cloud (`grid-cache`, `descriptor`, `embedding`, `completion`, `evaluation`,
`module-evaluation`, `cloud`, `module-placeholders`), and the renderer's models (`morph-codec`,
`restorer`, `morph-models`). The targets `catalog`, `cloud`, `morph` and `all` name groups of them,
and a run takes every step its targets need, in the order `steps/library.py` declares them.

**A step decides from what exists.** Progress lives with the outputs themselves. Just before it
would run, a step reads its inputs as named components -- the readable samples, the label texts, an upstream
artifact's content, its parameters -- and is satisfied when an output exists for exactly those
inputs (`steps/kinds.py`):

| Kind | Satisfied when |
|---|---|
| `PassStep` | always runs, its command skipping the work it already finished (`pass_completion`) |
| `GuardedPassStep` | the labels file's digest is recorded in `curation.annotation_import`; it refuses over labels of the library's own |
| `GrowingExperimentStep` | its key names an experiment and no readable sample is left for it to describe |
| `DerivedExperimentStep` | an experiment is filed under the key its inputs' digest names, and shown where it must be |
| `FileArtifactStep` | the artifact named by its inputs' digest stands complete with a sidecar recording those inputs |
| `PointerStep` | the library's record (the cloud's promotion, the published models) names this run's output |

A file artifact's sidecar (`<artifact>.pipeline.json`) holds the inputs, the content digest and the
file's fingerprint; an artifact complete by its own marker whose sidecar is missing is sealed
without a rerun. A training artifact is complete once `finished.json` stands beside its model, and a
run of the same inputs that stopped short continues with `--resume`. The descriptor is also sealed
under its content (`descriptor-<sha16>.pt`), which the learned experiment names, so an experiment
always loads the weights it was described by. Downstream inputs read upstream content, so a rerun
producing the same bytes leaves everything after it satisfied. Parameters digest over the validated
values of a step's settings model (`settings.py`), so a default written out, `40.0` for `40` and
reordered keys name the same outputs, and the digest reads the parameters alone, apart from the
ceiling, the device and the worker count.
`pipeline status` evaluates the same decisions without running anything, naming the components that
moved since a step's last record under `pipeline/steps`.

**Runs stop and resume.** The first step that fails, refuses, is interrupted or outgrows its ceiling
ends the run, every later step is recorded as unreached, and the command exits with that step's
status (1, 3, 130 or 4); a relaunch takes up there. A run holds a session advisory lock per library,
and every step's process holds a lock named for its step (`SAMPLELIBRARY_STEP_LOCK`), so a second run,
or a relaunch while an orphaned step still runs, is refused. A step runs in a session of its own
under its memory scope; the run passes Ctrl+C on to it once, terminates it on the second and kills
it on the third. Each run keeps `pipeline/runs/<time>-<id>/`: `events.jsonl`, `attempts.jsonl`, a
log per step and the configuration snapshot every step reads, so an edit made while a run goes on
reaches the next run. Every durable effect is made before the event reporting it, and the scheduler
holds no `finally` or exit that writes (`test_forward_only.py`), which is what makes a killed run
equal to one stopped at the same moment.

`--from-scratch` records its intent, resets the catalog, removes every output the steps own, and
removes the intent; a relaunch finding the intent finishes the removal first. `--redo STEP` drops a
file step's artifact, sidecar and training run, keeping its sealed copy.

**Scenarios prove it.** `tests/samplelibrary/pipeline/scenarios` runs the pipeline through its own
composition root (`run_pipeline_command`) in a process of its own over a small world of modules and
sample files. A scenario states, act by act, the verdict of every step, how the run ended, and which
parts of the catalog and the artifacts moved; every act is also held to the evidence the run left
(attempts, logs, the scripted steps' ledger), to what `status` said right before it, to a settled
status after it, and to no lock outliving it. Catalog passes run their real commands; the steps
reading the listening model or training a network run their real command lines against stand-ins
that write the real outputs (`harness/stand_ins.py`). Faults script a step's exit, a gate stops it
before, partway through or after its output for the scenario to interrupt or kill it, and a sink
kills the run's own process at a chosen event. `just test-pipeline` runs the same stories with every
real program on the processor, and `just explore-pipeline` draws sequences of acts with Hypothesis
(`test_exploration.py`) and holds every run to the same checks, shrinking a divergence to the
shortest sequence showing it.

## Deployment

Two packages run as long-lived services: `sampleserver`, the API, and `samplemorph.service`, the
morph inference process. `sampleextract` and `samplecloud` are one-shot offline batch commands,
run by hand or on a schedule, never by the served app itself. The root `Dockerfile` builds a
runtime image for the served app alone: a Node stage builds the frontend, and the Python stages
install only the `server` extra (`fastapi`, `uvicorn`, `httpx`) -- `sampleextract`/`samplecloud`'s
own heavier dependencies (`librosa`, `umap-learn`, `scikit-learn`) never reach that image, mirroring
the `sampleserver never imports the offline batch pipelines` import-linter contract above. The
image runs as an unprivileged user (uid 1000), so a mounted library has to be readable by it, which
objects written by this version are. The catalog names each sample directory by the path it was
scanned under, so a container serving samples from sample directories mounts each one read-only at
that same path, which the commented mount in `docker-compose.yml` shows. Its environment names the config at `/app/config.toml`
(`SAMPLELIBRARY_CONFIG`), the built frontend (`SAMPLELIBRARY_FRONTEND_DIRECTORY`) and four workers
(`WEB_CONCURRENCY`), and its command is `serve --host 0.0.0.0 --port 8000`, so a replacement command
keeps the frontend and the workers; the health check reads `/api/stats`, so a healthy container is one
whose catalog answers. The config mounted into it names `module_source_directory` and `library_root`
as paths inside the container, and `database_url` unless the environment supplies it.

The inference process (`samplelibrary morph serve`) installs the `morph` extra, reads the library
root, the sample directories its configuration lists and the fitted models, and opens no database: a
morph names two samples and a weight, and the API, which knows the catalog, reads each sample's
playback rate the way it does everywhere else, together with the file an end found only in sample
directories is read from — the first still as it was scanned, or a 404 before the process is dialed
when none is. The process reads a named file only inside its own sample directories, and only when
the file decodes to the hash the request names. Both processes read one setting, `[inference] url` in `config.toml`: the
process binds it, the API dials it, and a morph request reaching the API while no process answers
comes back as 503 with that address in its detail, a render outlasting the client's wait as 504, and
any other failure of the process as 502. Renders are deterministic given the files a route loads, so
each carries a validator built from a fingerprint over those files' digests, the vocoder, the morpher
and `RENDER_REVISION`, together with the point, under `Cache-Control: private, no-cache`: a browser
revalidates every play, and one holding the render is answered with a 304 by the process that made
it. A point whose ends are heard more than sixteen times apart in rate, or that would render past
`MAXIMUM_RENDER_FRAMES`, is refused with 422 before any rendering, and the render and latent caches
are bounded by the bytes they hold.

Every route the API serves sits under `/api` (`sampleserver.app.API_PREFIX`), so one path always
names one thing: the frontend reaches `/api/samples` while a person's browser holds `/samples/{hash}`
as a client route of its own. That is what lets the Vite dev server forward a single prefix to the
backend and answer everything else with the application itself, so reloading a sample's own URL
brings back the dashboard. `samplelibrary serve --frontend <dist>` does the same without Vite:
`sampleserver.frontend.SinglePageApplication` serves the built files and answers every other path
outside `/api` with `index.html`, and the image serves its own build this way. It is mounted through
`FrontendMount`, which takes no path under `/api`, so the API answers a wrong method with 405 and
its allowed methods, a trailing slash with its redirect, and an unknown path with its JSON 404,
whether or not a frontend is served beside it.

The dev server also grows the cloud on request: with `VITE_CLOUD_DENSIFY` set, a plugin in
`frontend/dev/` answers `/api/cloud` (and `/api/cloud/modules` under `VITE_CLOUD_DENSIFY_MODULES`)
with the backend's own points followed by seeded clones of them, laid out in Gaussian clusters and
each carrying its parent's hash and rate, so the sandbox's few dozen samples show the density of a
library of a hundred thousand and every interaction still reaches the catalog. A catalog whose
embedding has yet to run is laid out from its own listing first, one cluster per category its badge
names -- the hand label, else the first suggestion, else the first word of its name -- which keeps
every point on a real hash. The plugin runs under `vite` serve alone.

`samplelibrary serve` loads the configuration and opens the catalog once before uvicorn starts, so a
missing or incomplete config ends the start with one message and exit status 3, a database that
cannot be reached within ten seconds with one message and exit status 1, and
the catalog's schema is prepared once, under the schema lock, before any worker runs. Each worker's
own start prepares the curation schema under the same lock (`connect_for_curation`), so workers
starting together take turns.

`docker-compose.yml` adds a `postgres` service alongside it (a named volume for persistence), as a
worked example of the two running together. Its `sampleserver` mounts `LIBRARY_ROOT` (default
`./library`) at `/library` and `CONFIG_PATH` (default `docker/config.toml`, whose paths are the
container's own) at `/app/config.toml`, both read-only, supplies the database through
`SAMPLELIBRARY_DATABASE_URL`, and publishes the app on `127.0.0.1:8000`. A path either names that is
not there fails the start rather than mounting an empty directory. Its `extra_hosts` entry lets the
container reach a renderer running on the host at `http://host.docker.internal:8010`, the commented
`[inference]` table in `docker/config.toml`. A real deployment points
`database_url`/`SAMPLELIBRARY_DATABASE_URL` at whatever Postgres instance it actually runs against,
container or otherwise. `just docker-run <library> <config>` runs the image alone against a config
written for the container, which names its `database_url` and, for morphs, an `[inference] url` the
container reaches. On Linux the recipe shares the host's network and binds `127.0.0.1:8000`, so
`localhost` in that config means the host itself; on macOS and Windows it publishes
`127.0.0.1:8000`, and Docker Desktop names the host `host.docker.internal`. The recipe reads both
paths from the directory it was run in, and mounts them so that a path that is not there fails the
run. Local development runs
against a Postgres installed on the machine directly, which the test suite and both library
databases share. The container runs
`samplelibrary serve` with several worker processes (`WEB_CONCURRENCY`), where `just serve` starts the one
reloading process development uses: each worker holds a small pool of read-only Postgres
connections, checked out per request (`sampleserver.dependencies.get_connection`), which Postgres's
own concurrent-connection handling supports natively, so multiple people browsing the library
through one deployed server works correctly with no shared state between workers. The library's data
directory and a `config.toml` pointing at its in-container path are supplied at `docker run` time as
bind mounts, never baked into the image, mirroring `config.toml` never being committed to the
repository.

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
while one process held a write transaction open. A batch job (`samplelibrary extract`,
`equivalence`, `thumbnails`, `cloud embed`) can now run alongside `sampleserver` serving live
traffic without that exclusion; the operational concern that remains is a batch job's own resource
footprint on the host machine (CPU contention, not lock contention -- still worth timing a heavy
local run accordingly). `samplelibrary cloud embed` in particular writes into its own experiment
(`sample_feature_vector`, scoped by `experiment_id`) and never touches `sample_cloud_coordinates`
until `reduce_and_persist_coordinates`'s own explicit promotion step, so an in-progress extraction
run has no visible effect on what the server or other experiments see until that promotion happens.

### What the cloud costs

Measured on the real catalog of 127,588 samples over localhost on 2026-09-12, one uvicorn worker,
before and after each tier of the network work. The stages script
(`runs/cloud-2026-09-12/measure_stages.py` under the library root) times the server's own work
with no server running; `measure_routes.sh` beside it reads wire bytes and times off a running
`samplelibrary serve`; the browser's parse time is `JSON.parse` over the fetched text in the
console.

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
paints by them. The classification term in the build belonged to the keyword categories the points
carried then; the points now carry coordinates and rates alone, and the Cloud panel opens painted
by category from the suggestions, fetching `/api/cloud/suggestions` and the cached
`/api/cloud/suggestion-tags` as it mounts. Measured on the same body, gzip alone takes the cloud's response to 9 MB and the
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
changed extractor as a new experiment (`samplelibrary cloud embed --backend <name>`), inspect and
compare its result, and only promote it (`reduce_and_persist_coordinates` against that experiment's
id) once satisfied -- the previously promoted experiment's `sample_cloud_coordinates` stay exactly
as they were until that deliberate step. `samplelibrary cloud embed --backend <name> --extract-only`
runs the extraction alone, for an experiment made to be measured or to teach another descriptor;
`cloud embed --experiment-id N` resumes experiment N and promotes it.

An experiment records its recipe in its parameters (`samplecloud.experiments.EmbeddingRecipe`): the
backend, the `reading`, for a learned descriptor the model's name, and for the listening model the
commit of its checkpoint this build pins (`TEACHER_REVISION`), so an experiment heard through
another commit is refused rather than extended. An experiment may carry a key, unique across the
catalog (`experiment.key`): `cloud embed --key K` starts an experiment under K following the recipe
flags, and every later run naming K resumes it, and `morph embed --key K` writes its experiment and
every vector in one transaction, so an experiment a key names holds its whole cache. A resumed experiment follows
the recipe its own row records, so `--experiment-id` refuses a `--backend`, `--model` or
`--heard-rate` naming another, and a label, which names a new experiment. Before new vectors join an
experiment that already holds some, its first eight samples by hash are described again and must
point where their stored vectors do (`require_reproducible`), so a descriptor retrained under the
same name is refused rather than mixed in. `--resume-promoted` resumes the experiment `cloud_promotion`
names, opening and recording the default `librosa` experiment on a library with no cloud yet; a
promoting run that adds no vector to the experiment already shown keeps its layout as it is. A layout
needs at least four vectors, the fewest UMAP lays out.

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
listening model's rate invariance ends within a whole tone. A vector keeps the rate it was heard at
(`sample_feature_vector.heard_rate`, empty under the nominal reading), so a sample the library comes
to play at another rate -- a new module playing it, or a sample file declaring another rate beside its
occurrences -- is pending again, its vector replaced in the checkpoint that stores the new one, and
the reproducibility probe checks only samples still heard at their vectors' rates.

`samplelibrary cloud suggest` turns a `clap` experiment's vectors into labels. The text tower reads
a vocabulary of prompts in the hand-label grammar -- the shipped instrument list, the tags people
wrote, or a file with one label per line -- into the same space, one cosine per sample and label
ranks them, and each sample keeps its closest few under a new experiment of the `zero_shot` backend,
whose parameters name the source experiment, the checkpoint, the prompt template and the vocabulary
in order (`sample_label_suggestion`, `samplecore.storage.repositories.label_suggestion`). The
command reports how the first picks spread over the vocabulary and how they agree with the hand
labels, exactly and by category. Suggestions are rebuildable, so they live in the main schema beside
the feature vectors. `suggestion_promotion` names the scoring the application shows, and a scoring
writes its experiment, every suggestion and that record in one transaction, so a reader never meets
one half written. `--key` files a scoring under a name of its own: a later run naming the same key
and the same recipe shows that scoring again without loading the model, and one naming another
recipe is refused.

### Judging a descriptor

`samplecloud.evaluation` scores any experiment's vectors against three targets the catalog already
carries, so a change to an extractor is answered by numbers rather than by an impression.

- **Transposition retrieval** retunes a sample by a fixed mirrored grid of semitone offsets,
  describes the result, and reports where the original ranks against the whole catalog. It needs no
  label at all, since retuning produces a query the catalog holds the answer to. Rank-1 and rank-5
  shares travel beside the median rank, because a descriptor placing the original second every time
  and one placing it forty-thousandth both score zero at rank one.
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

`--scope modules` scores the samples tracker modules hold and leaves the ones found only in sample
directories out, fitting the standardization over that corpus alone, so a descriptor trained with a
sample pack and one trained without it are read over one body of samples; every report carries its
scope and a digest of the samples it scored, which the run store records beside the numbers.

Each metric reports the share of the catalog it describes, so a reader sees which part of the
library a score speaks for. Splits are grouped by equivalence class, which changes nothing while
`sample_relation` is empty and becomes correct on its own once it is not. One seed fixes every split
and every draw, so a second run reproduces every number. `samplelibrary cloud evaluate` records each
pass as a run in the tracking store beside the library (`samplecore.tracking`), one metric per
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

## Labels on a sample

A sample is named by two kinds of label. The hand label is what a person wrote
(`SampleSummary.hand_label`, and the same field on the detail and preview models); the suggested
label is what the listening model heard first, the closest pick of the scoring on show
(`suggested_label`, read per request through `first_pick_labels` in
`samplecore.storage.repositories.label_suggestion`, the shown scoring resolved once per request by
the `get_shown_experiment_id` dependency). Everywhere a sample is named the app calls this its
category, and `CategoryBadge` is the single place the rule is applied: the hand label wins in a solid
badge of its own, the first suggestion stands in a dashed one, and a sample neither names reads as
unlabeled. A suggestion badge carries a swatch in its top-level tag's color, from the same ranks the
cloud paints by, so a badge and its point agree; a label too long for its cell ends in an ellipsis
with the whole wording in its tooltip.

The cloud colors by the hand labels' own tags or by the suggestions, with nothing about any tag
known to the frontend. `GET /curation/annotations/tags` reads the tag tree out of the labels through
`samplecore.labeling`, each tag with its count and a rank by the order it was first used, and
`GET /cloud/labels` carries every labeled sample's tags in the order the person wrote them, apart
from the points because a few hundred labels change with every label written while a hundred
thousand points change only with the embedding. `GET /cloud/suggestions` carries each sample's first
suggested tag path with its score, apart from the points in the same way, and
`GET /cloud/suggestion-tags` the tags suggested first with their counts, each counting toward its
category and ranked by its place in the scoring's vocabulary; both answers are cached under the id of
the scoring on show, since a scoring's picks never change once written. The frontend paints a tag in
a color that is a function of its rank alone (`labelPalette.ts`: hues a golden angle apart, at the
lightness and chroma each theme declares), so a tag keeps its color as the vocabulary grows and a new
one takes the next hue; the legend is the picker, painting the most used top-level tags until a
person chooses their own, listing the painted ones with the rest behind a toggle inside a strip of at
most three rows, and a sample carrying several painted tags takes the first it was given
(`labelColoring.ts`). The Cloud panel opens in the category mode, painted from the suggestions, with
the labels one click away. Every point outside the painted tags joins the substrate, on its
recessive tone, and while a mode's sources load every point waits there.

A sample's detail lists every pick of the scoring on show as its categories (`SampleDetail.suggestions`,
closest first), each a dashed badge with its score beneath the label editor: a click appends the tag
to the hand label through `useAnnotationWriter`, the one write path every annotation gesture takes,
reaching the sample's near-duplicates the way the editor's own default does, and a tag the label
already holds shows as taken.

## The cloud on screen

`frontend/src/cloud/CloudView.tsx` draws the cloud as a stack of layers inside `.cloud-wrap`, which
paints the theme's ground. From the bottom:

| Layer | Drawn by | Shows |
|---|---|---|
| `canvas.cloud-underlay` | `useUnderlay`, on a 2D canvas | the grid, and the density glow under a theme that declares one |
| `canvas.cloud-dots` | `regl-scatterplot` | every point as a dot; the pointer target for panning, zooming, hit-testing and selection |
| `canvas.cloud-nodes` | `useNodeLayer` and `hollowPointRenderer.ts`, on WebGL through `regl` | every point as a hollow square or ring of one size at every zoom |
| `svg.cloud-markers` | `CloudMarkers` | the hovered and the selected point, each in the theme's point shape |
| overlays | `CloudView`, `MorphBand`, `MorphLink` | the ping locating a highlighted point, the pairing band and the morph link |

Every layer moves within the frame that draws the points. The scatterplot publishes its `drawing`
event synchronously inside the animation frame rendering a moved view, and `CloudView` answers it,
and every resize of the container, in one pass (`syncView`): it derives a `ViewTransform` from the
camera matrix (`viewTransform.ts`), repaints the underlay and the node layer through it, and commits
the overlays' positions from `getScreenPosition` through `flushSync`, so the frame paints dots,
nodes, grid and markers from one view. With `W` and `H` the container's size in CSS pixels and
`view` the column-major camera matrix, the scatterplot places a data point `(x, y)` at

```
screenX = W/2 + (H/2) * (view[0] * x + view[4] * y + view[12])
screenY = H/2 - (H/2) * (view[1] * x + view[5] * y + view[13])
```

Half the height is one clip unit on both axes, which keeps the data square in a panel of any aspect.

The scatterplot draws each palette slot at a size and opacity of its own, the substrate's slot
first, finer and fainter, so the named points stand on a ground whose density still shows. The
active and hover colors arrive as one color per slot, which paints a selected or hovered categorical
point in the theme's own selection and hover colors. The library compiles the point shape into its
shaders at creation, so a theme that changes `--cloud-point-shape` recreates the scatterplot with its
camera carried over.

`--cloud-node-mode` sets when the node layer takes over from the dots, through a short crossfade of
the two canvases (`.cloud-wrap-nodes`): `always` at every zoom, and `detail` once the view holds at
most as many points as markers covering 30% of the surface (`detailLevel.ts`). The node shader
places every frame on the device's pixel grid, so a one-pixel outline stays crisp at any pixel ratio,
and paints it from the palette the dots use, the substrate at `--cloud-node-substrate-opacity`.

The grid's lines stand a power of two apart in data units, the smallest step keeping them at least
`--cloud-grid-spacing` pixels apart (`gridSpacing.ts`), so a zoom halves or doubles the grid in
place; every line is a row, every fourth a beat and every sixteenth a measure, each rank in its own
color, drawn on both axes or as vertical lines with a zero line across `y = 0`. The glow, under a
theme with a positive `--cloud-glow-opacity`, is one image built whenever the points or their colors
change (`densityGlow.ts`): the named points counted into a 256 by 256 field over the normalized data
domain, blurred by three box passes, each cell in the average color of its points and as opaque as
the logarithm of its count. The underlay stretches that image over the screen box its domain covers.

Every visual value above is a CSS custom property in `styles.css` (`--cloud-point-*`,
`--cloud-substrate-*`, `--cloud-marker-*`, `--cloud-node-*`, `--cloud-grid-*`, `--cloud-glow-opacity`,
`--cloud-link-*`, `--cloud-band-dash`, `--cloud-ping-*`, `--cloud-hover-color`), so the themes differ
in tokens alone: `cloudRenderSettings.ts` reads the ones the canvases use into one
`CloudRenderSettings` whenever the theme changes, and the SVG overlays take theirs through CSS. The
dark and light themes draw round dots over their substrate, rings in detail, cased markers and a
solid accent link. The OpenMPT theme draws its envelope editor: a black ground, a vertical grid,
every point a hollow square in its painted tag's color at every zoom, the selected point yellow and the
morph pair joined by a yellow line. A system dark preference applies the dark block beneath a chosen
OpenMPT theme as well, so the OpenMPT block declares every token the dark block declares.

## Morphs in the application

A morph is a pair of samples and a weight between them, held in `frontend/src/morph/morphStore.ts`
apart from the shell's focus and highlight: the pairing gestures alone fill it, so it stays where it
was put while a person goes on browsing. The cloud fills the pair with the right
mouse button, which regl-scatterplot leaves alone (it pans and selects on the left button only), so
the browser's menu is the one thing `CloudView` keeps off the canvas: a right-drag from one point to
another joins the two, and a right-click on a point joins it to the sample in hand. A Shift-click on
a sample row makes the same join from a listing, both reading the anchor through `morphAnchorOf` in
`frontend/src/workspace/selectionStore.ts`: the highlighted sample, or the focused one.
While the button is held, a band runs from the point the drag started at, or from that sample when
the press landed on empty space, to the cursor, snapping to the point under it
(`frontend/src/cloud/MorphBand.tsx`), so the pair a release would join is visible before it lands;
the join then draws a line between the two ends' markers with a knob on it that is the weight
(`frontend/src/cloud/MorphLink.tsx`), moving with the points through pan and zoom like every overlay
on the cloud. The Morph
panel mirrors the same weight as a slider, names both ends with the
link every listing row carries (a click highlights the end, a double-click opens it in the Sample
Detail), and plays the render on release through the one preview element every sample plays
through (`useAudioPreview`, whose sources carry a URL and a key, so a morph is keyed by its own
render's address). Beneath the play row it states how far apart the two ends sit
(`frontend/src/morph/MorphDistance.tsx`, over `GET /samples/{hash}/distance/{other}`), so the length
of the path is read where the path is traveled. Both ends are carried into one frame before they blend: the API resolves the
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
