# SampleLibrary

A personal library and web app for the samples inside tracker modules (XM, IT, MOD, S3M), and for
folders of plain audio files beside them. It collects every sample from your module collection and
your sample folders, drops exact duplicates, groups near-duplicates together, and lets you browse,
label and rate them — including a visual "cloud" of the whole library.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 17 or later, Docker to run one in a container, or neither: the `app` extra carries a
  server the library runs by itself
- Node.js 25.9 or later, and npm, for the frontend
- [just](https://just.systems/) 1.56 or later, which runs the setup and everyday recipes;
  `uv tool install rust-just` installs it
- An NVIDIA GPU, to train the descriptor that lays out the cloud. A library that takes the bundled
  descriptor instead (see `descriptor_source` below) runs on the processor alone, only more slowly.
- About a gigabyte of disk for the pretrained listening model the `clap` cloud backend downloads
  on first use. `just install` installs every extra, this one included.

## Setup

```sh
git clone --recurse-submodules https://github.com/JakimPL/SampleLibrary.git
cd SampleLibrary
just install
```

`just install` also creates `config.toml`. Open it and set two paths: where your modules are, and
where extracted samples should go. Folders of sample packs are optional and can be added at any time
(see [Configuration](#configuration)).

No PostgreSQL on the machine? Delete the `database_url` line from `config.toml`, and `just database`
creates a server of the library's own inside `library_root` and starts it. Alternatively,
`docker compose up -d postgres` starts one on port 5432. If that port is
taken, put another in a file named `.env` beside `docker-compose.yml`, such as `POSTGRES_PORT=5433`:
compose reads it every time it starts the container, so the port stays the same. Set the same port in
`database_url` in `config.toml`. Then create the databases:

```sh
just database
```

That makes sure the PostgreSQL server `config.toml` names holds three databases, one role owning
them all: your library, `samplelibrary_dev` for the development sandbox, and `samplelibrary_test`
for the test suite. It creates whichever of the role and the databases are missing, then adds any
missing tables to the library and the sandbox; rows already there stay as they are, so it is safe
to run at any time. If a step needs something from you — a PostgreSQL superuser, usually — it prints
the exact statement to run, and you run `just database` again afterwards. On a server where those
database names belong to someone else, create your library's database alone with
`createdb -O <role> <name>`: the first extraction adds its tables.

## Configuration

`config.toml` holds your own machine's settings and stays out of the repository. An installed copy of
the application keeps it in your user settings folder instead, and writes it for you. These keys sit
under its `[library]` table:

- `module_source_directory`: your module collection, read with every folder inside it. A library of
  sample folders alone leaves it out.
- `library_root`: where extracted audio, the trained descriptor and recorded runs are kept.
- `database_url`: the PostgreSQL connection. The `SAMPLELIBRARY_DATABASE_URL` environment variable
  takes precedence over it, except for a command given `--config`, which reads everything from the
  file it names. Left out, the library keeps its own server in `library_root/postgres`, listening on
  this machine alone.
- `minimum_sample_frames`: the shortest sample extraction keeps, 512 frames by default.
- `sample_directories`: folders of WAV, AIFF and FLAC files to add to the library, such as
  `["/home/you/Samples/Packs"]`. Their files are read where they are, so they keep taking up disk
  space in their own folders alone. Each folder must stand apart from the others.
- `sample_exclusions`: patterns for files and folders inside those folders to leave out, such as
  `["*loop*"]`. Each pattern is matched against a path relative to its folder, ignoring case, and
  `*` also matches across folders.

The `[inference]` table holds one key, `url`: the address the morph renderer listens on and the API
reaches it at, `http://127.0.0.1:8010` by default. It names a port of its own.

`morph.yaml`, in `src/samplemorph/routes/selections/`, is committed and names the morph the renderer plays, and
`morph-filter.yaml` beside it names the one the morph filter is read under. The renderer reads both,
so one process plays the morph and hands over the filter; see
[Morphing two samples](#morphing-two-samples).

The optional `[pipeline]` table holds the settings `just rebuild` builds the library with:

- `memory_cap`: the memory ceiling every step runs under, such as `"16G"`; `"none"` by default.
- `device` and `workers`: the device training and the descriptor run on, and how many processes a
  pass spreads over. `"auto"`, the default, picks an NVIDIA card when there is one and the processor
  otherwise.
- `descriptor_source`: `"trained"` (the default) trains the descriptor on your own library;
  `"pretrained"` takes the one bundled with the application and skips the training, together with
  the listening pass and the scores only training needs. Libraries the app creates start with
  `"pretrained"`. `just bundle-descriptor` bundles your library's current descriptor, so the next
  build of the app ships it.
- `labels`: a file of hand labels, as `annotations export` writes it, read into a fresh library.
- A table per step, such as `[pipeline.descriptor]`, sets that step's parameters (`epochs = 40`) and
  its own `memory_cap`. `config.example.toml` shows the shape.

Paths take forward slashes or your system's own separator; a backslash is written twice, as in
`"C:\\Users\\you\\Modules"`.

## Usage

```sh
just rebuild         # fill the library from your modules
just serve           # start the API
just frontend-dev    # start the frontend in a second terminal, then open http://localhost:5173
```

`just app` runs everything in one process instead: the library's database, the API with the built
frontend (`just frontend-build`), and the morph renderer, opened in your browser. Without a config
file it opens on pages that ask for your folders and write the config for you.

`just rebuild` builds the whole library in one command: it reads your modules and sample folders
into the catalog, finds near-duplicates, draws thumbnails, hears every sample with the listening
model and gives it a category, teaches the descriptor, and lays out the cloud. Run it again whenever you add modules or samples: every step checks what it
was built from, and only the steps whose inputs changed run again, so a library that stands still
is done in moments. `just rebuild catalog` and `just rebuild cloud` build one part and whatever it needs. `just status` says what each step would do now and why.

A run that fails or is interrupted with Ctrl+C stops at that step, and the next `just rebuild` picks
up there: extraction keeps the modules it finished, and training continues from its last epoch. Each
run keeps its log files and a record of every step under `pipeline/runs` in your library root.
`uv run samplelibrary pipeline run --from-scratch` empties the catalog and everything the pipeline
built, keeping your labels, and builds it all again; `--redo descriptor` teaches the descriptor again
on its own. Extraction takes a while over a large collection, so it spreads itself across your
machine's cores. `uv run samplelibrary extract --prune` also removes the modules whose
files are gone from your collection, with the samples only they held; it refuses when a file or a
folder could not be read, so a disconnected drive empties nothing.

Sample folders are scanned by `uv run samplelibrary files`. A second scan reads only the files that
changed since the last one. Because the files stay where
they are, a sample whose file has gone missing — a deleted file, an unplugged drive — stays in the
library: the app marks it unavailable, and every pass skips it and picks it up again once the file
is back. `uv run samplelibrary files --prune` removes the files that are gone, the ones your
exclusions now leave out, and every file of a folder you took out of `sample_directories`. Like
extraction, it refuses when a configured folder is missing or empty, so an unplugged drive empties
nothing.

Every operation on the library is a `samplelibrary` command: `uv run samplelibrary --help` lists
them, and each command's own `--help` lists its options — `uv run samplelibrary extract --workers 2`
holds extraction to two processes, for example. Any command takes `--memory-cap 16G`, which holds it
and every process it starts to that much memory, so a pass that outgrows the machine is stopped and
the machine stays up: Linux holds it in a systemd user scope, Windows in a job object.
`just capped <command>` passes a 16 GB ceiling for you, and `just rebuild` holds every step to the
`memory_cap` of the `[pipeline]` table. A system offering neither way to hold a process runs the
command only with a ceiling of `none`.

Near-duplicate detection is a command of its own, `uv run samplelibrary equivalence`. It reads every
sample once into a short fingerprint, then compares only the samples whose fingerprints are alike,
in under three gigabytes of memory; over 127,588 samples it took two and a quarter hours on one
core, and an interrupted run keeps what it finished.

`just reset` empties the catalog and the stored audio, and `just rebuild` fills the library again;
your labels, models and training runs are kept throughout.

Everything listens on this machine alone:

| Service | Address | To change it |
|---|---|---|
| API | `127.0.0.1:8000` | `uv run samplelibrary serve --port <port>` |
| Frontend | `localhost:5173` | Vite picks the next free port; it reaches the API through `VITE_BACKEND_DEV_URL` |
| Morph renderer | `127.0.0.1:8010` | `[inference] url` in `config.toml` |
| MLflow | `127.0.0.1:5000` | `uv run samplelibrary tracking ui --port <port>` |

To point the frontend at an API on another port, set `VITE_BACKEND_DEV_URL` before starting it:
`VITE_BACKEND_DEV_URL=http://127.0.0.1:8001 just frontend-dev` in a POSIX shell, or
`$env:VITE_BACKEND_DEV_URL = "http://127.0.0.1:8001"; just frontend-dev` in PowerShell. To reach the
app from another device, run `npm run dev -- --host` inside `frontend`; anyone on your network can
then change your labels, since the app asks nobody to sign in.

The sandbox library holds a few dozen samples, too few to show how the cloud behaves at the size of a
real library. `VITE_CLOUD_DENSIFY=100000 VITE_BACKEND_DEV_URL=http://127.0.0.1:8001 just frontend-dev`
grows the sandbox's cloud to a hundred thousand points while the frontend runs under Vite; every added
point borrows a real sample's identity, so hovering, playing and morphing keep working. A library with
no embedding yet is laid out from its own samples, a cluster per category, so the view fills either way.
`VITE_CLOUD_DENSIFY_MODULES` does the same for the Modules tab.

`just frontend-build` builds the frontend for production, and
`uv run samplelibrary serve --frontend frontend/dist`, run in place of `just serve`, serves it
together with the API at `http://127.0.0.1:8000`. The Docker image does the same;
`docs/architecture.md` describes running it. The API describes its own routes at
`http://127.0.0.1:8000/api/docs`.

## Using it on a phone

The same app fits a phone. Start the frontend so that other devices can reach it, and open the
address Vite prints on a phone on the same network:

```sh
just frontend-dev-lan    # the same as `npm run dev -- --host` inside frontend
```

Below 768 pixels of width the app shows three tabs along the bottom, Samples, Cloud and Modules,
with a tray above them naming the sample or module in hand: its stars, its heart and the › that
opens it, all on one row; a double tap on its name opens it as well. A tap on a row takes the
sample in hand and plays it; a held row offers
its label. A sample or a module opens as a page of its own, whose ‹ and › walk the listing, so
labeling a run of samples is one page after another; a sample's page plays it from one row over
its detail, at the rate the library plays it, with the file to save at the row's end. On the cloud, a tap plays a point, a drag moves, a
pinch zooms, a hold opens a point's actions, and the Legend button opens the legend with the
choice of what colors the points, categories or labels. The page itself keeps its size under a
finger, so a pinch and a double tap always reach the cloud and the tray. The morph lives under the cloud as two
slots, A and B: tap one, and every sample you tap next becomes that end (see
[Morphing two samples](#morphing-two-samples)). The More menu on each tab lists the statistics,
the theme, a guide to every gesture and the diagnostics, which say what the browser's WebGL
supports: the cloud's own renderer blends every point into a float buffer, and a browser without
that draws the points as plain dots by itself, a choice the diagnostics also offer outright. A
tablet keeps the desktop's panels with controls at a finger's size. The browser's "Add to Home
Screen" installs the app with its own icon.

Everything a phone does goes through the same API as the desktop; the app asks nobody to sign in,
so anyone on your network who reaches it can change your labels.

## Recipes

| Recipe | What it does |
|---|---|
| `just install` | Installs the Python and frontend dependencies and the git hooks, and puts `config.toml` in place |
| `just database` | Creates the role and the library, sandbox and test databases on the configured server, wherever they are missing |
| `just rebuild [targets]` | Builds the library, or the `catalog` or `cloud` part of it, running only the steps whose inputs changed |
| `just status [targets]` | Says what each step of the library would do now, and why |
| `just app` | Runs the library's database, the API with the built frontend, and the morph renderer, and opens them in a browser |
| `just bundle-descriptor` | Copies the configured library's trained descriptor into the package, as the one new libraries take |
| `just package <trackmod>`, `just executable`, `just publish-trackmod` | Prepare the wheels and pinned requirements, build the PyApp executable, and upload trackmod to PyPI (see [Development](#development)) |
| `just serve` | Starts the API, restarting it whenever the code changes |
| `just serve-inference` | Starts the morph renderer the API reaches for morphs (see [Morphing two samples](#morphing-two-samples)) |
| `just tracking-ui` | Opens MLflow over the runs every training and evaluation pass recorded |
| `just capped <command>` | Runs a `samplelibrary` command under a 16 GB memory ceiling; `just MEMORY_CAP=24G capped …` raises it |
| `just reset` | Names the library and database it would empty, then empties the catalog and stored audio once you confirm; labels, ratings, favorites, models and runs stay |
| `just check` | Formats, lints and tests the Python code and the frontend |
| `just format`, `just lint`, `just test`, `just coverage` | Runs one part of the Python checks; `coverage` also reports the lines the tests leave unrun |
| `just test-pipeline` | Builds a tiny library with every real program, the listening model and training included, on the processor |
| `just explore-pipeline` | Acts on a small library in orders drawn at random for a few minutes, holding every run of the pipeline to its checks |
| `just frontend-install`, `just frontend-dev`, `just frontend-dev-lan` | Installs the frontend's dependencies; starts its development server, on this machine alone or for every device on the network |
| `just frontend-check`, `just frontend-build`, `just frontend-types` | Checks the frontend, builds it for production, and regenerates its API types from the schema |
| `just dev-build`, `just dev <command>`, `just serve-dev`, `just dev-reset` | Writes a sandbox of 30 modules, 300 one-shots and ten labels in `dev-library` and builds it, runs a `samplelibrary` command on it, serves it on port 8001, and empties its database and deletes its files |
| `just docker-build`, `just docker-run <library> <config>` | Builds the app's image, and runs it over a library directory and a config written for the container, both read from where you run the recipe |

The sandbox shares the PostgreSQL server `config.toml` names, under its own `samplelibrary_dev`
database, so `just dev-build` needs your configuration in place first. To browse it, start the
frontend with `VITE_BACKEND_DEV_URL=http://127.0.0.1:8001`.

The morph renderer lives in the `samplemorph` package and the learned descriptor the cloud embeds
with in `sampledescriptor`; the descriptor's commands (`uv run samplelibrary descriptor --help`) cache
the sounds' grids, teach the descriptor and describe the library through it.

## Morphing two samples

The app can play a sound between any two samples, through a morph renderer running beside the API:

```sh
uv run samplelibrary morph serve                      # the renderer, in a terminal of its own
```

`src/samplemorph/routes/selections/morph.yaml` says what the renderer plays; edit it and start the renderer
again. Every morph moves the spectral envelope from one sample's to the other's through the samples'
own spectral analyses, and nothing needs fitting. As committed, both samples' harmonics sound under
the moving envelope and slide from the first sample's pitch to the second's (`excitation: both` with
`glide: subharmonic`). `excitation: first` keeps only the first sample's harmonics along the whole
path and `excitation: second` only the second's; dropping `glide` holds every harmonic where it
stands, so the morph arrives at its new pitch at the far end instead of gliding there. A pair glides
only where both samples read a pitch the reader trusts, so drums and noise sound as they would
without it.

A plugin or any other program can play its own audio through a morph instead of asking the renderer
for each point. Held to one sample, the morph is a filter on it, and the whole path between two
samples fits in a few numbers per frame that a caller applies at any weight:

```sh
uv run samplelibrary morph response --first <hash> --second <hash> \
  --selection src/samplemorph/routes/selections/morph-filter.yaml --output pair.bin
```

`morph-filter.yaml` is the settings file both that command and the renderer read a filter under. A
filter describes a path whose harmonics stay where they are, so it holds every pitch where
`morph.yaml` glides. A program asks the running renderer for the same filter instead, by sending it
two audio files of its own, which is how the SampleMorpher plugin plays a morph of any two samples.

`just serve-inference` starts the renderer on whatever `morph.yaml` names, and `--selection` points
it at another file, as `--filter-selection` does for the filter. The renderer needs the `morph` extra alone, so it runs on a machine without the
training libraries.

With the renderer running, the strip under the cloud holds the two ends of a morph, A and B, by
these rules:

1. A and B are the two ends of the morph, each a slot under the cloud.
2. Click or tap a slot to select it. A selected slot plays its sample and takes it in hand, and
   every sample you tap next, in a list or on the cloud, becomes that end, until you tap the slot
   again or select the other one. A sample already at the other end trades places. An empty slot
   at rest reads "take" and the name of the sample in hand; one click or tap makes that sample the
   end, and the slot stays at rest.
3. × lets an end go; ⇄ swaps the ends and mirrors the weight. A selected slot stays selected
   through both.
4. Once both ends are chosen, the slider stands under the row, and the morph is drawn at the
   slider's point right away, unheard, so the ends themselves are heard first. The waveform button
   opens a waveform beneath it, laid out as a sample's player is and at its height: the morph drawn
   over both ends, or a lone chosen end's own player.
5. The marker on the cloud and the slider are one weight: let either go and that point plays and
   is drawn over both originals, with the distance between the two samples stated on a desktop.
6. On a desktop, the right mouse button pressed on one point and released on another, a right-click
   on a point, a Shift-click on a row or the M key also pair, with the sample you last clicked as A.

The two ends play as the route renders them, so with the first sample's harmonics kept the far end
is the second sample's spectral shape over the first sample's notes. Without the renderer running,
the strip says so and offers to check again.

## Development

Read `docs/guidelines.md` before making changes. `just check` runs formatting, linting and tests;
`just frontend-check` does the same for the frontend. The tests run against the `samplelibrary_test`
database on the server `config.toml` names; `SAMPLELIBRARY_TEST_DATABASE_URL` names another one. `docs/architecture.md` describes the package
layout and how the project uses its databases.

Packaging the application takes two recipes, run on each system it is built for:

```sh
just package "trackmod==0.2.0"   # dist/: both wheels, the frontend inside, and app-requirements.txt
just executable                  # dist/SampleLibrary(.exe), built with PyApp; needs Rust (rustup)
```

`just package` builds the frontend into the samplelibrary wheel, beside the descriptor
`just bundle-descriptor` put in place, and writes the locked versions of the `app` extra with
torch's processor build. `just executable` pins those versions into a copy of the wheel and compiles
a PyApp launcher around it. On first start the executable downloads Python and installs the pinned
application with uv, which takes several minutes; later starts take seconds. The installed app needs
no Node, no PostgreSQL and no checkout.

trackmod has to be on PyPI for the executable to install; `just publish-trackmod` uploads it (uv asks
for a PyPI token). To try an executable before that, `just executable --find-links dist` lets its
first start install trackmod from the wheel in `dist/`.
