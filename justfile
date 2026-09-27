set minimum-version := "1.56.0"
set default-list := true

[windows]
set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

MEMORY_CAP := "16G"
TEST_WORKERS := "8"
QUICK_TESTS := "not pipeline_real and not pipeline_explore and not pipeline_scenario"
DEV_CONFIG := "dev-library/config.toml"
DEV_PORT := "8001"
SCHEMAS := "build/schemas"
CAPPED_SAMPLERIPPER := "uv run sampleripper --memory-cap " + MEMORY_CAP

[group("setup")]
install: && frontend-install
    uv sync --all-extras --all-groups
    uv run pre-commit install --hook-type pre-commit --hook-type pre-push
    uv run sampleripper setup config

[group("setup")]
database:
    uv run sampleripper setup database

[group("quality")]
format:
    uv run isort src tests scripts notebooks
    uv run black src tests scripts notebooks

[group("quality")]
lint:
    uv run codespell
    uv run mypy
    uv run pylint src scripts
    uv run lint-imports

# The tests but the pipeline scenarios, which `test-all` and `test-scenarios` run.
[group("quality")]
test:
    uv run pytest -n auto --maxprocesses {{ TEST_WORKERS }} -m "{{ QUICK_TESTS }}"

[group("quality")]
test-all:
    uv run pytest -n auto --maxprocesses {{ TEST_WORKERS }}

[group("quality")]
test-scenarios:
    uv run pytest -n auto --maxprocesses {{ TEST_WORKERS }} -m pipeline_scenario tests/sampleripper/pipeline/scenarios

[group("quality")]
test-pipeline:
    uv run pytest -m pipeline_real tests/sampleripper/pipeline/scenarios/real

[group("quality")]
explore-pipeline:
    uv run pytest -m pipeline_explore tests/sampleripper/pipeline/scenarios/test_exploration.py

[group("quality")]
coverage:
    uv run pytest --cov --cov-report=term-missing

# Every check a push needs, marking the commit they passed on; the pre-push hook lets that commit through.
[group("quality")]
check: _check-start _hooks lint test-all frontend-check
    uv run --no-project python scripts/checked_commits.py record

[private]
_check-start:
    uv run --no-project python scripts/checked_commits.py start

[private]
_hooks:
    uv run pre-commit run --all-files

[group("library")]
app:
    uv run sampleripper app

[group("library")]
serve:
    uv run sampleripper serve --reload

[group("library")]
serve-inference:
    uv run sampleripper morph serve

[group("library")]
tracking-ui:
    uv run sampleripper tracking ui

[group("library")]
rebuild *targets:
    uv run sampleripper pipeline run {{ targets }}

[group("library")]
status *targets:
    uv run sampleripper pipeline status {{ targets }}

[group("library")]
[unix]
[positional-arguments]
capped *arguments:
    {{ CAPPED_SAMPLERIPPER }} "$@"

[group("library")]
[windows]
[positional-arguments]
[script("powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File")]
capped *arguments:
    {{ CAPPED_SAMPLERIPPER }} @args
    exit $LASTEXITCODE

[group("library")]
reset: && _reset-confirmed
    uv run sampleripper reset

[confirm("Empty the library named above?")]
_reset-confirmed:
    uv run sampleripper reset --confirm

[group("dev")]
dev-build *targets:
    uv run python scripts/build_dev_library.py
    uv run sampleripper --config {{ DEV_CONFIG }} pipeline run {{ targets }}

[group("dev")]
[unix]
[positional-arguments]
dev *arguments:
    uv run sampleripper --config {{ DEV_CONFIG }} "$@"

[group("dev")]
[windows]
[positional-arguments]
[script("powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File")]
dev *arguments:
    uv run sampleripper --config {{ DEV_CONFIG }} @args
    exit $LASTEXITCODE

[group("dev")]
serve-dev:
    uv run sampleripper --config {{ DEV_CONFIG }} serve --reload --port {{ DEV_PORT }}

# The SampleRipper app on the sandbox, which records labels where `serve-dev` only reads.
[group("dev")]
app-dev:
    uv run sampleripper --config {{ DEV_CONFIG }} app --port {{ DEV_PORT }}

[group("dev")]
[unix]
dev-reset:
    if [ -f {{ DEV_CONFIG }} ]; then uv run sampleripper --config {{ DEV_CONFIG }} reset --confirm; fi
    rm -rf dev-library

[group("dev")]
[windows]
dev-reset:
    if (Test-Path {{ DEV_CONFIG }}) { uv run sampleripper --config {{ DEV_CONFIG }} reset --confirm }
    if (Test-Path dev-library) { Remove-Item -Recurse -Force dev-library }

[group("frontend")]
[working-directory("frontend")]
frontend-install:
    npm install

[group("frontend")]
[working-directory("frontend")]
frontend-dev:
    npm run dev

[group("frontend")]
[working-directory("frontend")]
frontend-dev-lan:
    npm run dev -- --host

[group("frontend")]
[working-directory("frontend")]
frontend-build:
    npm run build

[group("frontend")]
[working-directory("frontend")]
frontend-check:
    npm run typecheck
    npm run lint
    npm run format:check
    npm test

[group("frontend")]
frontend-types: (_directory SCHEMAS)
    uv run sampleripper schema --output {{ SCHEMAS }}/openapi.json
    uv run sampleripper setup-schema --output {{ SCHEMAS }}/setup-openapi.json
    npm --prefix frontend run types

[group("release")]
package:
    uv run --no-project python scripts/build_package.py

[group("release")]
executable:
    uv run --no-project python scripts/build_app.py

[group("release")]
installer:
    uv run --no-project --with pillow python scripts/build_installer.py

[group("release")]
release-descriptor tag *arguments:
    uv run python scripts/release_descriptor.py --tag {{ tag }} {{ arguments }}

[unix]
_directory path:
    mkdir -p "{{ path }}"

[windows]
_directory path:
    New-Item -ItemType Directory -Force -Path "{{ path }}" | Out-Null

# The passwords docker-compose.yml reads, each written once into docker/ and readable by you alone.
[group("docker")]
docker-secrets:
    uv run python scripts/docker_secrets.py

[group("docker")]
docker-build:
    docker build -t sampleripper-site .

# Publish a library into the database docker-compose.yml runs, such as `just docker-publish --config dev-library/config.toml`.
[group("docker")]
docker-publish *arguments:
    uv run python scripts/docker_publish.py {{ arguments }}
