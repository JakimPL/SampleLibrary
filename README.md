# SampleLibrary

A personal library and web application for tracker music samples, extracted from XM, IT, MOD, and
S3M modules. It deduplicates identical sample content by hash, groups near-duplicate samples into
reviewable equivalence classes (bit-depth conversions, resampled variants), and lets you browse
modules, samples, and their cross-references, including a visual "cloud" of the whole library.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) for dependency management
- PostgreSQL 17 or later, running locally
- Node.js and npm (for the frontend, added from Phase 6 onward)

## Setup

```sh
git clone --recurse-submodules <this repository>
cd SampleLibrary
cp config.example.toml config.toml   # then edit config.toml with your local paths
make install
```

`config.toml` holds machine-specific paths (where your module collection lives, where extracted
samples are stored) and is never committed.

### Database

The project keeps three databases on one PostgreSQL server: your real library, the disposable
development library, and one the test suite owns. Create them once, along with the role they share:

```sql
CREATE ROLE samplelibrary WITH LOGIN CREATEDB PASSWORD 'samplelibrary';
CREATE DATABASE samplelibrary OWNER samplelibrary;
CREATE DATABASE samplelibrary_dev OWNER samplelibrary;
CREATE DATABASE samplelibrary_test OWNER samplelibrary;
```

Each pipeline creates its own tables the first time it connects. Point `database_url` in
`config.toml` at your real library; the `SAMPLELIBRARY_DATABASE_URL` environment variable overrides
it, which is how the `*-dev` targets in the `Makefile` reach the development library instead. The
test suite reads `SAMPLELIBRARY_TEST_DATABASE_URL`, and otherwise connects to `samplelibrary_test`
on localhost with the credentials above. It gives each of its parallel workers a database of its
own, created and dropped around the run, which is what the `CREATEDB` grant is for.

## Usage

The extraction pipeline, embedding pipeline, and web application are introduced incrementally;
see `docs/architecture.md` for the current package layout and `Makefile` for the available
commands (`make extract`, `make embed`, `make serve`, and so on) as each phase lands.

Extraction takes a couple of hours over a large collection. To split it, run `make extract
SHARD=0/4` through `SHARD=3/4` in four terminals, or on four machines pointed at one database:
each takes a quarter of the files, and between them they cover the collection once.

Work on generating audio from a point between two samples is documented separately, under
`docs/morphing/`, starting from `docs/morphing/00-handover.md`.

### Frontend

`make install` also installs the frontend's npm dependencies. With the API running (`make
serve`), start the frontend in a separate terminal with `make frontend-dev` and browse
`http://localhost:5173`. `make frontend-build` produces a production build; `make frontend-check`
runs its typecheck, lint, format, and test suite.

### Labeling and rating samples by hand

Open a sample in the app and type what it actually is. The wording is yours to choose, and what
you have already used is offered back as you type, so one vocabulary settles by habit. Beside it,
five stars record what you make of the sample and a heart keeps it in your own collection; both
save the moment you click them. Where a sample has near-duplicates the same decision reaches all
of them by default.

The samples list can then show only your favorites, or only what you rated at least a given
number, or put the best-rated first. Those reach the whole library rather than the rows already on
screen, so a collection scattered across a hundred thousand samples still browses as one.

These decisions are the one thing here that nothing can rebuild, so they are kept apart from
everything the pipelines generate: they live in their own `curation` schema, and `make
reset-library` leaves them exactly where they are. `make annotations-export` writes them all to
`annotations.jsonl` — keep a copy somewhere of your own — and `make annotations-import` reads a
file back, merging it into whatever is already there. Each one also remembers the module and slot
its sample came from, so `make annotations-relink` reattaches your work if a sample's hash ever
changes.

## Development

Read `docs/guidelines.md` before making changes. `make format`, `make lint`, and `make test` (or
`make check` for all three) validate a change; `make coverage` reports test coverage.
