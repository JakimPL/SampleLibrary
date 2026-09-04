# SampleLibrary

A personal library and web application for tracker music samples, extracted from XM and IT
modules (MOD and S3M planned). It deduplicates identical sample content by hash, groups
near-duplicate samples into reviewable equivalence classes (bit-depth conversions, resampled
variants), and lets you browse modules, samples, and their cross-references, including a visual
"cloud" of the whole library.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) for dependency management
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

## Usage

The extraction pipeline, embedding pipeline, and web application are introduced incrementally;
see `docs/architecture.md` for the current package layout and `Makefile` for the available
commands (`make extract`, `make embed`, `make serve`, and so on) as each phase lands.

## Development

Read `docs/guidelines.md` before making changes. `make format`, `make lint`, and `make test` (or
`make check` for all three) validate a change; `make coverage` reports test coverage.
