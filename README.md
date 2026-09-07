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

### Frontend

`make install` also installs the frontend's npm dependencies. With the API running (`make
serve`), start the frontend in a separate terminal with `make frontend-dev` and browse
`http://localhost:5173`. `make frontend-build` produces a production build; `make frontend-check`
runs its typecheck, lint, format, and test suite.

## Development

Read `docs/guidelines.md` before making changes. `make format`, `make lint`, and `make test` (or
`make check` for all three) validate a change; `make coverage` reports test coverage.
