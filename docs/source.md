# Running from source

This guide is for running SampleLibrary from a checkout of its repository. It covers building your
library with commands, every setting, and each service the app runs on. The installed app does all
of this for you; the [README](../README.md) shows how to get it.

## Requirements

- Python 3.12 or later, and [uv](https://docs.astral.sh/uv/).
- [just](https://just.systems/) 1.56 or later, which runs the recipes below. `uv tool install
  rust-just` installs it; `rust-just` is its name on PyPI.
- Node.js 25.9 or later, and npm, for the web app.
- A PostgreSQL 17 server of your own, or Docker to run one, or neither: the library then runs a
  server of its own inside its folder.
- An NVIDIA GPU, for building the cloud in reasonable time: it listens to every sample, and trains
  the descriptor that lays out the cloud unless the version carries a published one
  (`descriptor_source` below). The processor alone builds it too, far more slowly.
- About 1 GB of disk for the listening model, downloaded the first time a build needs it.

## Setup

```sh
git clone --recurse-submodules https://github.com/JakimPL/SampleLibrary.git
cd SampleLibrary
just install
```

`just install` installs the Python and web dependencies and the git hooks, and creates
`config.toml`. Open it and set where your modules are and where the library keeps its files
(see [Configuration](#configuration)).

For the database, pick one of three:

- **The library's own server.** Delete the `database_url` line from `config.toml`, and
  `just database` creates a server inside `library_root` and starts it.
- **A server in Docker.** `docker compose up -d postgres` starts one on port 5432. For another
  port, put it in a file named `.env` beside `docker-compose.yml`, such as `POSTGRES_PORT=5433`,
  and set the same port in `database_url`.
- **A server you already run.** Set `database_url` to it.

Then create the databases:

```sh
just database
```

It makes sure the server holds your library's database, `samplelibrary_dev` for the development
sandbox and `samplelibrary_test` for the tests, all owned by one role. It also creates the two roles
the API connects as, one that reads and one that also records your labels, each allowed nothing
more. It creates whatever is missing and keeps every row already there, so it is safe to run at any
time. When a step needs a
PostgreSQL superuser, it prints the statement to run; run `just database` again afterwards. On a
server where those names belong to someone else, create your library's database alone with
`createdb -O <role> <name>`: the first scan adds its tables.

## Configuration

`config.toml` holds your machine's settings and stays out of the repository;
`config.example.toml` shows every key. Paths take forward slashes or your system's own separator,
and a backslash is written twice, as in `"C:\\Users\\you\\Modules"`.

The `[library]` table:

- `module_source_directory`: your module collection, read with every folder inside it. A library of
  sample folders alone leaves it out.
- `library_root`: where the library keeps its extracted audio, models and recorded runs.
- `database_url`: the PostgreSQL connection. The `SAMPLELIBRARY_DATABASE_URL` environment variable
  takes its place, except for a command given `--config`, which reads everything from the file it
  names. Left out, the library runs its own server in `library_root/postgres`, listening on this
  machine alone.
- `server_database_url` and `curation_database_url`: on a server of your own, the roles
  `samplelibrary serve` and the SampleLibrary app connect as. The first reads the library, the second
  also records your labels, and neither may change anything else; `just database` creates both with
  the names and passwords these URLs hold. `SAMPLELIBRARY_SERVER_DATABASE_URL` and
  `SAMPLELIBRARY_CURATION_DATABASE_URL` take their places. A library running its own server creates
  its roles itself.
- `minimum_sample_frames`: the shortest sample the library keeps, 512 frames by default.
- `sample_directories`: folders of WAV, AIFF and FLAC files to add, such as
  `["/home/you/Samples/Packs"]`. Their files are read where they are, and each folder stands apart
  from the others.
- `sample_exclusions`: patterns for files and folders inside those folders to leave out, such as
  `["*loop*"]`. Each pattern is matched against a path relative to its folder, ignoring case, and
  `*` also matches across folders.

The `[inference]` table holds `url`: the address the morph renderer listens on and the API reaches
it at, `http://127.0.0.1:8010` by default. The SampleLibrary app starts its own renderer on this
address, or on another port of the same host when a program already holds this one.

The `[pipeline]` table holds what `just rebuild` builds the library with, every key optional:

- `memory_cap`: the memory ceiling every step runs under, such as `"16G"`; `"none"` by default.
- `device` and `workers`: the device training runs on, and how many processes a pass spreads over.
  `"auto"`, the default, picks an NVIDIA card when there is one and the processor otherwise.
- `descriptor_source`: `"automatic"`, the default, downloads the published descriptor where this
  version carries one, about 2 MB, and teaches one on your own library otherwise. `"trained"` and
  `"pretrained"` name one of the two outright.
- `labels`: a file of hand labels, as `annotations export` writes it, read into a fresh library.
- A table per step, such as `[pipeline.descriptor]`, sets that step's parameters (`epochs = 40`) and
  its own `memory_cap`. The listening steps, `teacher` and `hearing-teacher`, take `batch_size`: how
  many samples the listening model hears at once, 16 by default. A larger batch keeps a graphics
  card busier, and a smaller one fits a card with less memory.

## Building the library

```sh
just rebuild           # everything: the catalog and the cloud
just rebuild catalog   # the modules and sample folders alone
just status            # what each step would do now, and why
```

`just rebuild` reads your modules and sample folders into the catalog, finds near-duplicates, draws
thumbnails, gives every sample a category with the listening model, teaches the descriptor and lays
out the cloud. Run it again whenever your collection grows: every step checks what it was built
from, and only the steps whose inputs changed run again.

A run that fails or that you stop with Ctrl+C stops at that step, and the next `just rebuild` picks
up there. Each run keeps its logs and a record of every step under `pipeline/runs` in your library
root. `uv run samplelibrary pipeline run --from-scratch` empties the catalog and everything the
pipeline built, keeping your labels, and builds it all again; `--redo descriptor` teaches the
descriptor again on its own.

Every operation on the library is a `samplelibrary` command: `uv run samplelibrary --help` lists
them, and each command's `--help` lists its options. A few you will reach for:

- `uv run samplelibrary extract --prune` removes the modules whose files left your collection, with
  the samples only they held.
- `uv run samplelibrary files` scans the sample folders again, reading only the files that changed.
  `files --prune` removes the files that are gone, the ones your exclusions now leave out, and every
  file of a folder you took out of `sample_directories`.
- `uv run samplelibrary equivalence` finds near-duplicates on its own.

Both prunes go ahead only when every folder reads and every configured folder holds files, so a
disconnected drive keeps its samples in the library. A sample whose file is missing stays in the library, marked
unavailable, and comes back once the file does.

Any command takes `--memory-cap 16G`, which holds it and every process it starts to that much
memory: Linux holds it in a systemd user scope, and Windows in a job object; on macOS, keep the
ceiling at `none`. `just capped <command>` passes a 16 GB ceiling for you. `just reset` empties the catalog and the stored audio
once you confirm, keeping your labels, ratings, favorites, models and runs; `just rebuild` fills
the library again.

## Running the app

`just app` runs everything in one process: the library's database, the API with the built web app,
and the morph renderer, opened in your browser. Build the web app once with `just frontend-build`.
When no config file is there yet, it opens on the setup page, which writes one for you. It listens
on the port it used last, or on a free one, and `--port` picks one. `uv run samplelibrary app
--quit` ends it. The checkout's config and the installed app's config each run an app of their own.

To work on the app, run its parts in terminals of their own:

```sh
just serve             # the API, restarting whenever the code changes
just serve-inference   # the morph renderer
just frontend-dev      # the web app; open http://localhost:5173
```

| Service | Address | To change it |
|---|---|---|
| API | `127.0.0.1:8000` | `uv run samplelibrary serve --port <port>` |
| Web app in development | `localhost:5173` | Vite picks the next free port |
| Morph renderer | `127.0.0.1:8010` | `[inference] url` in `config.toml` |
| MLflow | `127.0.0.1:5000` | `uv run samplelibrary tracking ui --port <port>` |

To point the development web app at an API on another port, set `VITE_BACKEND_DEV_URL` before
starting it: `VITE_BACKEND_DEV_URL=http://127.0.0.1:8001 just frontend-dev` in a POSIX shell, or
`$env:VITE_BACKEND_DEV_URL = "http://127.0.0.1:8001"; just frontend-dev` in PowerShell.
`uv run samplelibrary serve --frontend build/frontend` serves the built web app together with the
API at `http://127.0.0.1:8000`. The API describes its routes at `http://127.0.0.1:8000/api/docs`.

`just tracking-ui` opens MLflow over the runs every training and evaluation pass recorded.

## Phones and other devices

```sh
just frontend-dev-lan
```

This starts the web app for every device on your network; open the address it prints on your phone.
[Using SampleLibrary](using.md#phones-and-tablets) describes the app on a phone. The API `just
serve` runs reads the library and changes nothing, so every device on the network sees your labels
as they are; you change them in `just app` on the computer it runs on.

## The morph renderer

`src/samplemorph/routes/selections/morph.yaml` says what the renderer plays; edit it and start the
renderer again. Every morph moves the spectral envelope from one sample's to the other's. As
committed, both samples' harmonics sound under the moving envelope and glide from the first
sample's pitch to the second's (`excitation: both` with `glide: subharmonic`). `excitation: first`
keeps the first sample's harmonics along the whole path, and `excitation: second` the second's.
With `glide` removed, every harmonic holds its pitch and the morph arrives at the new pitch at
the far end. A pair glides where both samples have a pitch the reader trusts, so drums and noise sound as
they are.

A plugin or another program can play its own audio through a morph. Held to one sample, the morph
is a filter on it, and the whole path between two samples fits in a few numbers per frame that a
caller applies at any weight:

```sh
uv run samplelibrary morph response --first <hash> --second <hash> \
  --selection src/samplemorph/routes/selections/morph-filter.yaml --output pair.bin
```

`morph-filter.yaml` is the settings file both that command and the renderer read a filter under,
and it holds every pitch where it stands. A program can also send the running renderer two audio
files of its own and get the filter back, which is how the SampleMorpher plugin plays a morph of
any two samples. `just serve-inference` starts the renderer on `morph.yaml`; `--selection` points
it at another file, as `--filter-selection` does for the filter. The renderer needs only the
`morph` extra, so a machine with that extra alone runs it.

## Docker

`just docker-build` builds an image of the API with the built web app, and
`just docker-run <library> <config>` runs it over a library folder and a config written for the
container, both read from where you run the recipe. `docker compose up` runs the image beside a
PostgreSQL container, with `LIBRARY_ROOT` and `CONFIG_PATH` naming the library folder and the config
it mounts. The architecture's [Deployment](architecture.md#deployment) section describes what
the image holds and what to mount.

## Recipes

| Recipe | What it does |
|---|---|
| `just install` | Installs the Python and web dependencies and the git hooks, and puts `config.toml` in place |
| `just database` | Creates the roles and the library, sandbox and test databases wherever they are missing |
| `just rebuild [targets]` | Builds the library, or its `catalog` or `cloud` part, running only the steps whose inputs changed |
| `just status [targets]` | Says what each step would do now, and why |
| `just app` | Runs the database, the API with the built web app and the morph renderer, opened in a browser |
| `just serve`, `just serve-inference` | Start the API and the morph renderer |
| `just frontend-build` | Builds the web app into `build/frontend` |
| `just frontend-dev`, `just frontend-dev-lan` | Start the development web app, on this machine alone or for every device on the network |
| `just tracking-ui` | Opens MLflow over the recorded runs |
| `just capped <command>` | Runs a `samplelibrary` command under a 16 GB ceiling; `just MEMORY_CAP=24G capped …` raises it |
| `just reset` | Empties the catalog and the stored audio once you confirm, keeping labels, ratings, favorites, models and runs |
| `just docker-build`, `just docker-run <library> <config>` | Build the image, and run it over a library folder and a config |

[Development](development.md) lists the recipes for checks, tests and the sandbox, and
[Building and releasing](building.md) the ones that build the executable and the installers.
