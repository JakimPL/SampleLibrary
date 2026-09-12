# SampleLibrary

A personal library and web app for the samples inside tracker modules (XM, IT, MOD, S3M). It
collects every sample from your module collection, drops exact duplicates, groups near-duplicates
together, and lets you browse, label and rate them — including a visual "cloud" of the whole
library.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 17 or later
- Node.js 25.9 or later, and npm, for the frontend
- An NVIDIA GPU, to train the restorer that turns a morph back into sound and the descriptor that
  lays out the cloud. Everything else in the project runs on the processor alone.
- About a gigabyte of disk for the pretrained listening model the `clap` cloud backend downloads
  on first use. `make install` installs every extra, this one included.

## Setup

```sh
git clone --recurse-submodules git@github.com:JakimPL/SampleLibrary.git
cd SampleLibrary
make install
```

`make install` also creates `config.toml`. Open it and set two paths: where your modules are, and
where extracted samples should go. Then create the databases:

```sh
make database
```

If that needs something from you — a PostgreSQL superuser, usually — it prints the exact command to
run, and you run `make database` again afterwards. It is safe to run at any time, and leaves
anything that already exists alone.

No PostgreSQL on the machine? `docker compose up -d postgres` starts one. If port 5432 is taken,
use `POSTGRES_PORT=5433` and set the same port in `config.toml`.

## Usage

```sh
make extract       # scan your modules and fill the library
make serve         # start the API
make serve-inference  # start the morph renderer the API dials, in a second terminal
make frontend-dev  # start the frontend, then open http://localhost:5173
```

Extraction takes a while over a large collection, so it spreads itself across your machine's
cores. `make extract WORKERS=2` holds it to two processes if you want the machine back while it
runs.

`make notes` reads what your modules actually play, which is what lets the app sound a sample at the
speed the music does — run it after extraction, and again whenever you add modules. The `Makefile`
lists the rest of the pipeline: `make embed`, `make thumbnails` and so on.

Work on generating audio from a point between two samples lives in the `samplemorph` package,
one module per command under `samplemorph.commands`: fitting a linear codec, teaching the restorer
that puts back what the grid smooths away before a morph is made audible, caching the canonical
grids, teaching a descriptor and a codec that decodes from it, describing the library through a
descriptor, and rendering a listening set. The research behind
it is documented separately under `docs/morphing/`, starting from `docs/morphing/00-handover.md`.

That package installs PyTorch built for CUDA 12.8, which is a large download and the reason
`make install` takes a while the first time. It needs a card new enough for that build; an older one
installs cleanly and then fails the moment it is first asked to compute.

## Labeling and rating samples

Click a sample's category in the list and type what it is; words you have used before are suggested
as you type, and Enter records it. Labels are kept in capitals, so one wording stays one label
however you typed it. Emptying the field brings back the app's own guess. Five stars
and a heart sit in the same row, saved as you click, and a sample's own page offers all three as
well. Near-duplicates get the same decision by default, whenever the list has them grouped. The
samples list can then show only your favorites, or put your best-rated first, across the whole
library.

Labels, ratings and favorites are the one thing here that nothing can rebuild, so they are kept
apart from everything the pipelines generate, and `make reset-library` leaves them alone.
`make annotations-export` writes them to `annotations.jsonl` — keep a copy of your own — and
`make annotations-import` reads one back. `make annotations-relink` reattaches them if a sample's
hash ever changes.

The listening model can suggest labels for every sample. `make cloud-teacher HEARD=1` describes
the catalog with it, hearing each sample at the rate it is played at (about an hour), and
`make cloud-suggest EXPERIMENT=<that experiment's id>` ranks a vocabulary of instruments against
every sample in minutes; `VOCABULARY=hand-labels` ranks the wordings you have used instead, and a
file with one label per line works too. The cloud then colors by suggestion, and a sample's page
lists its suggestions with the model's confidence: a click adds one to the label, and the rest
stay suggestions.

## Morphing two samples

The app can play a sound between any two samples. Start the morph renderer beside the API
(`make serve-inference`; it reads the fitted models under your library root, which the `samplemorph`
pipeline writes), then click one sample in the cloud and Shift-click another: a dashed line joins
them, and the marker on it is how far from the first sample toward the second you stand. Drag the
marker, or move the slider in the Morph panel, and the morph plays when you let go. The two ends
play as the model reconstructs them, with each original one click away beside its name. Without the
renderer running, the panel says so and offers to check again.

## Development

Read `docs/guidelines.md` before making changes. `make check` runs formatting, linting and tests;
`make frontend-check` does the same for the frontend. `docs/architecture.md` describes the package
layout and how the project uses its databases.
