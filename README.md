# SampleLibrary

A personal library and web app for the samples inside tracker modules (XM, IT, MOD, S3M). It
collects every sample from your module collection, drops exact duplicates, groups near-duplicates
together, and lets you browse, label and rate them — including a visual "cloud" of the whole
library.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 17 or later
- Node.js and npm, for the frontend

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
make frontend-dev  # start the frontend, then open http://localhost:5173
```

Extraction takes a couple of hours over a large collection. To split it, run `make extract
SHARD=0/4` through `SHARD=3/4` in four terminals, or on four machines pointed at one database.

The `Makefile` lists the rest of the pipeline: `make embed`, `make thumbnails` and so on.

## Labeling and rating samples

Open a sample in the app and type what it is; words you have used before are suggested as you type.
Five stars and a heart record what you think of it, saved as you click. Near-duplicates get the same
decision by default. The samples list can then show only your favorites, or only what you rated at
least a given number, across the whole library.

Labels, ratings and favorites are the one thing here that nothing can rebuild, so they are kept
apart from everything the pipelines generate, and `make reset-library` leaves them alone.
`make annotations-export` writes them to `annotations.jsonl` — keep a copy of your own — and
`make annotations-import` reads one back. `make annotations-relink` reattaches them if a sample's
hash ever changes.

## Development

Read `docs/guidelines.md` before making changes. `make check` runs formatting, linting and tests;
`make frontend-check` does the same for the frontend. `docs/architecture.md` describes the package
layout and how the project uses its databases.
