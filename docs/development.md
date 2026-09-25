# Development

This guide is for contributors: the checks every change passes, the tests, the sandbox library, and
where generated files go. Set up a checkout first, as [Running from source](source.md) shows.

## Before you change code

Read [the guidelines](guidelines.md): they set the code's style, typing, error handling and
documentation rules. [The architecture](architecture.md) maps which package owns what, and how the
project uses its databases.

## Checks

`just check` runs everything a change has to pass: formatting, linting and tests for the Python code,
then the same for the web app. Its parts run on their own too:

- `just format`: isort and black.
- `just lint`: codespell, mypy, pylint and import-linter.
- `just test`: the test suite, spread over every core; `just coverage` also reports the lines the
  tests leave unrun.
- `just frontend-check`: type checking, ESLint, Stylelint, Prettier and the web app's tests.

`just install` sets up git hooks: formatting and spelling run on every commit, and type checking,
linting and the tests on every push. The push hook fails on any pylint message, even while pylint's score reads
10.00, so read its messages or its exit status.

## Tests

The tests run against the `samplelibrary_test` database on the server `config.toml` names;
`SAMPLELIBRARY_TEST_DATABASE_URL` names another one. Two slower suites run on their own:

- `just test-pipeline` builds a tiny library with every real program, the listening model and
  training included, on the processor.
- `just explore-pipeline` acts on a small library in orders drawn at random for a few minutes,
  holding every run of the pipeline to its checks.

## The sandbox library

`just dev-build` writes a sandbox of 30 modules, 300 one-shots and ten labels into `dev-library/`
and builds it, in the `samplelibrary_dev` database on your configured server. `just dev <command>`
runs a `samplelibrary` command on it, `just serve-dev` serves it on port 8001, and `just dev-reset`
empties its database and deletes its files.

To browse it, start the web app with `VITE_BACKEND_DEV_URL=http://127.0.0.1:8001 just frontend-dev`.
The sandbox holds a few dozen samples; `VITE_CLOUD_DENSIFY=100000` added to that command grows its
cloud to a hundred thousand points, each borrowing a real sample's identity, so hovering, playing
and morphing work on every point. `VITE_CLOUD_DENSIFY_MODULES` does the same for the Modules tab.

## The web app

The web app lives in `frontend/`: React, built with Vite. `just frontend-install` installs its
packages, and `just frontend-dev` runs it with changes applied as you save.

Its API types are generated from the API itself. After changing a route or a model the API
returns, run `just frontend-types`: it writes both OpenAPI schemas into `build/schemas/` and
regenerates `frontend/src/api/schema.ts` and `setupSchema.ts`, which are committed.

## Where generated files go

Source folders hold source alone. Everything generated goes to one of three top-level folders:

```
build/                    intermediate files, safe to delete
  frontend/               the built web app: `just app` serves it, the wheel and the Docker image copy it
  schemas/                the OpenAPI schemas `just frontend-types` reads
  package/                the wheel and its pinned requirements, which `just executable` reads
bin/                      the executable `just executable` builds
dist/                     the files a release publishes
```

The folder of the built web app is named in three places: `frontend/vite.config.ts` writes it, and
`src/samplecore/paths.py` and `hatch_build.py` read it. [Building and releasing](building.md)
describes `bin/` and `dist/`.

## Recipes

| Recipe | What it does |
|---|---|
| `just check` | Formats, lints and tests the Python code and the web app |
| `just format`, `just lint`, `just test`, `just coverage` | Run one part of the Python checks |
| `just test-pipeline` | Builds a tiny library with every real program, on the processor |
| `just explore-pipeline` | Runs the pipeline in random orders for a few minutes, checking every run |
| `just frontend-install`, `just frontend-check` | Install the web app's packages, and check it |
| `just frontend-types` | Regenerates the web app's API types from the API |
| `just dev-build`, `just dev <command>`, `just serve-dev`, `just dev-reset` | Build the sandbox, run a command on it, serve it on port 8001, and remove it |
