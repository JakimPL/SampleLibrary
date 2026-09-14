# SampleLibrary

A personal library and web app for the samples inside tracker modules (XM, IT, MOD, S3M). It
collects every sample from your module collection, drops exact duplicates, groups near-duplicates
together, and lets you browse, label and rate them — including a visual "cloud" of the whole
library.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 17 or later, or Docker to run one in a container
- Node.js 25.9 or later, and npm, for the frontend
- [just](https://just.systems/) 1.56 or later, which runs the setup and everyday recipes;
  `uv tool install rust-just` installs it
- An NVIDIA GPU, to train the restorer that turns a morph back into sound and the descriptor that
  lays out the cloud. Everything else in the project runs on the processor alone.
- About a gigabyte of disk for the pretrained listening model the `clap` cloud backend downloads
  on first use. `just install` installs every extra, this one included.

## Setup

```sh
git clone --recurse-submodules https://github.com/JakimPL/SampleLibrary.git
cd SampleLibrary
just install
```

`just install` also creates `config.toml`. Open it and set two paths: where your modules are, and
where extracted samples should go (see [Configuration](#configuration)).

No PostgreSQL on the machine? `docker compose up -d postgres` starts one on port 5432. If that port is
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

`config.toml` holds your own machine's settings and stays out of the repository. These keys sit
under its `[library]` table:

- `module_source_directory`: your module collection, read with every folder inside it.
- `library_root`: where extracted audio, fitted models and recorded runs are kept.
- `database_url`: the PostgreSQL connection. The `SAMPLELIBRARY_DATABASE_URL` environment variable
  takes precedence over it, except for a command given `--config`, which reads everything from the
  file it names.
- `minimum_sample_frames`: the shortest sample extraction keeps, 512 frames by default.

The `[inference]` table holds one key, `url`: the address the morph renderer listens on and the API
reaches it at, `http://127.0.0.1:8010` by default. It names a port of its own.

Paths take forward slashes or your system's own separator; a backslash is written twice, as in
`"C:\\Users\\you\\Modules"`.

## Usage

```sh
just rebuild         # fill the library from your modules
just serve           # start the API
just frontend-dev    # start the frontend in a second terminal, then open http://localhost:5173
```

`just rebuild` runs the passes the app reads, one after another: extraction, the notes your modules
play (which set the speed a sample sounds at), waveform thumbnails, and the cloud's layout. Run it
again whenever you add modules: extraction, notes and thumbnails pick up the new ones, and the cloud
describes the new samples the way it described the rest and lays itself out again; with nothing new,
the cloud stays as it is. Extraction takes a while over a large collection, so it spreads itself
across your machine's cores. `uv run samplelibrary extract --prune` also removes the modules whose
files are gone from your collection, with the samples only they held; it refuses when a file or a
folder could not be read, so a disconnected drive empties nothing.

Every operation on the library is a `samplelibrary` command: `uv run samplelibrary --help` lists
them, and each command's own `--help` lists its options — `uv run samplelibrary extract --workers 2`
holds extraction to two processes, for example. On Linux, `just rebuild` and `just capped <command>`
run under a memory ceiling, so the kernel stops a pass that outgrows the machine and the machine
stays up; this uses a systemd user session. On macOS and Windows `just rebuild` runs the same passes
without a ceiling, and `just capped` is Linux's alone.

Near-duplicate detection is a command of its own, `uv run samplelibrary equivalence`. It reads every
sample once into a short fingerprint, then compares only the samples whose fingerprints are alike,
in under three gigabytes of memory; over 127,588 samples it took two and a quarter hours on one
core, and an interrupted run keeps what it finished.

`just reset` empties the catalog and the stored audio. To fill the library again, run `just rebuild`,
then `uv run samplelibrary equivalence`, and `uv run samplelibrary cloud suggest` for label
suggestions; your labels, models and training runs are kept throughout.

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

`just frontend-build` builds the frontend for production, and
`uv run samplelibrary serve --frontend frontend/dist`, run in place of `just serve`, serves it
together with the API at `http://127.0.0.1:8000`. The Docker image does the same;
`docs/architecture.md` describes running it. The API describes its own routes at
`http://127.0.0.1:8000/api/docs`.

## Recipes

| Recipe | What it does |
|---|---|
| `just install` | Installs the Python and frontend dependencies and the git hooks, and puts `config.toml` in place |
| `just database` | Creates the role and the library, sandbox and test databases on the configured server, wherever they are missing |
| `just rebuild` | Extracts your modules, reads their notes, draws thumbnails and lays out the cloud, capped on Linux |
| `just serve` | Starts the API, restarting it whenever the code changes |
| `just serve-inference` | Starts the morph renderer the API reaches for morphs (see [Morphing two samples](#morphing-two-samples)) |
| `just tracking-ui` | Opens MLflow over the runs every training and evaluation pass recorded |
| `just capped <command>` | Runs a `samplelibrary` command under a 16 GB memory ceiling, on Linux alone; `just MEMORY_CAP=24G capped …` raises it |
| `just reset` | Names the library and database it would empty, then empties the catalog and stored audio once you confirm; labels, ratings, favorites, models and runs stay |
| `just check` | Formats, lints and tests the Python code and the frontend |
| `just format`, `just lint`, `just test`, `just coverage` | Runs one part of the Python checks; `coverage` also reports the lines the tests leave unrun |
| `just frontend-install`, `just frontend-dev` | Installs the frontend's dependencies; starts its development server |
| `just frontend-check`, `just frontend-build`, `just frontend-types` | Checks the frontend, builds it for production, and regenerates its API types from the schema |
| `just dev-build`, `just dev <command>`, `just serve-dev`, `just dev-reset` | Builds a 30-module sandbox in `dev-library` and fills its catalog, runs a `samplelibrary` command on it, serves it on port 8001, and empties its database and deletes its files |
| `just docker-build`, `just docker-run <library> <config>` | Builds the app's image, and runs it over a library directory and a config written for the container, both read from where you run the recipe |

The sandbox shares the PostgreSQL server `config.toml` names, under its own `samplelibrary_dev`
database, so `just dev-build` needs your configuration in place first. To browse it, start the
frontend with `VITE_BACKEND_DEV_URL=http://127.0.0.1:8001`.

Work on generating audio from a point between two samples lives in the `samplemorph` package,
one module per command under `samplemorph.commands`: fitting a linear codec, teaching the restorer
that puts back what the grid smooths away before a morph is made audible, caching the canonical
grids, teaching a descriptor and a codec that decodes from it, describing the library through a
descriptor, and rendering a listening set. The research behind
it is documented separately under `docs/morphing/`, starting from `docs/morphing/00-handover.md`.

That package installs PyTorch built for CUDA 12.8, which is a large download and the reason
`just install` takes a while the first time. It needs a card new enough for that build; an older one
installs cleanly and then fails the moment it is first asked to compute.

## Labeling and rating samples

Click a sample's category in the list and type what it is; words you have used before are suggested
as you type, and Enter records it. Labels are kept in one spelling — capitals, one space after each
colon and comma, each tag once — so one wording stays one label however you typed it. Emptying the field brings back the app's own guess. Five stars
and a heart sit in the same row, saved as you click, and a sample's own page offers all three as
well. Near-duplicates get the same decision by default, whenever the list has them grouped. The
samples list can then show only your favorites, or put your best-rated first, across the whole
library.

Labels, ratings and favorites are the one thing here that nothing can rebuild, so they are kept
apart from everything the pipelines generate, and `just reset` leaves them alone.
`uv run samplelibrary annotations export` writes them to `annotations.jsonl` — keep a copy of your
own — and `annotations import` reads one back. `annotations relink` reattaches them if a sample's
hash ever changes.

The listening model can suggest labels for every sample.
`uv run samplelibrary cloud embed --backend clap --extract-only --heard-rate` describes the catalog
with it, hearing each sample at the rate it is played at (about an hour), and
`uv run samplelibrary cloud suggest --experiment-id <that experiment's id>` ranks a vocabulary of
instruments against every sample in minutes; `--vocabulary hand-labels` ranks the wordings you have
used instead, and a file with one label per line works too. The cloud then colors by suggestion, and
a sample's page lists its suggestions with the model's confidence: a click adds one to the label,
and the rest stay suggestions.

## Morphing two samples

The app can play a sound between any two samples, through a morph renderer running beside the API.
The renderer reads models fitted to your library, so it needs one first:

```sh
uv run samplelibrary morph fit                        # a linear codec, a few minutes on the processor
uv run samplelibrary morph serve --vocoder pghi       # the renderer, in a terminal of its own
```

The fit reads 4,000 samples between 4,000 and 200,000 frames long, in about three gigabytes of
memory, and keeps 256 components, so a library holding fewer such samples fits with a smaller
`--latent-size`; the command names the largest that fits.

`just serve-inference` starts the renderer with the restored vocoder, which sounds closer to the
original and needs a restorer trained on a GPU first: `uv run samplelibrary morph train-restorer`
takes about an hour an epoch over a large library.

With the renderer running, in the cloud, press the right mouse button on one sample and release it
on another: a line follows your cursor while the button is down, and the release joins the two with
a dashed line whose marker is how far from the first sample toward the second you stand. A plain
right-click on a sample joins it to the one you last clicked instead. Drag the marker, or move the
slider in the Morph panel, and the morph plays when you let go. The two ends play as
the model reconstructs them, with each original one click away beside its name, and a double-click
on either name opens it in the Sample Detail. Without the renderer running, the panel says so and
offers to check again.

## Development

Read `docs/guidelines.md` before making changes. `just check` runs formatting, linting and tests;
`just frontend-check` does the same for the frontend. The tests run against the `samplelibrary_test`
database on the server `config.toml` names; `SAMPLELIBRARY_TEST_DATABASE_URL` names another one. `docs/architecture.md` describes the package
layout and how the project uses its databases.
