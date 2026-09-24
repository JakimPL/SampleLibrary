set minimum-version := "1.56.0"
set default-list := true

[windows]
set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

MEMORY_CAP := "16G"
DEV_CONFIG := "dev-library/config.toml"
DEV_PORT := "8001"
CAPPED_SAMPLELIBRARY := "uv run samplelibrary --memory-cap " + MEMORY_CAP

[group("setup")]
install: && frontend-install
    uv sync --all-extras --all-groups
    uv run pre-commit install --hook-type pre-commit --hook-type pre-push
    uv run samplelibrary setup config

[group("setup")]
database:
    uv run samplelibrary setup database

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

[group("quality")]
test:
    uv run pytest -n auto

[group("quality")]
test-pipeline:
    uv run pytest -m pipeline_real tests/samplelibrary/pipeline/scenarios/real

[group("quality")]
explore-pipeline:
    uv run pytest -m pipeline_explore tests/samplelibrary/pipeline/scenarios/test_exploration.py

[group("quality")]
coverage:
    uv run pytest --cov --cov-report=term-missing

[group("quality")]
check: format lint test frontend-check

[group("library")]
app:
    uv run samplelibrary app

[group("library")]
bundle-descriptor *arguments:
    uv run python scripts/bundle_descriptor.py {{ arguments }}

[group("library")]
serve:
    uv run samplelibrary serve --reload

[group("library")]
serve-inference:
    uv run samplelibrary morph serve

[group("library")]
tracking-ui:
    uv run samplelibrary tracking ui

[group("library")]
rebuild *targets:
    uv run samplelibrary pipeline run {{ targets }}

[group("library")]
status *targets:
    uv run samplelibrary pipeline status {{ targets }}

[group("library")]
[unix]
[positional-arguments]
capped *arguments:
    {{ CAPPED_SAMPLELIBRARY }} "$@"

[group("library")]
[windows]
[positional-arguments]
[script("powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File")]
capped *arguments:
    {{ CAPPED_SAMPLELIBRARY }} @args
    exit $LASTEXITCODE

[group("library")]
reset: && _reset-confirmed
    uv run samplelibrary reset

[confirm("Empty the library named above?")]
_reset-confirmed:
    uv run samplelibrary reset --confirm

[group("dev")]
dev-build *targets:
    uv run python scripts/build_dev_library.py
    uv run samplelibrary --config {{ DEV_CONFIG }} pipeline run {{ targets }}

[group("dev")]
[unix]
[positional-arguments]
dev *arguments:
    uv run samplelibrary --config {{ DEV_CONFIG }} "$@"

[group("dev")]
[windows]
[positional-arguments]
[script("powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File")]
dev *arguments:
    uv run samplelibrary --config {{ DEV_CONFIG }} @args
    exit $LASTEXITCODE

[group("dev")]
serve-dev:
    uv run samplelibrary --config {{ DEV_CONFIG }} serve --reload --port {{ DEV_PORT }}

[group("dev")]
[unix]
dev-reset:
    if [ -f {{ DEV_CONFIG }} ]; then uv run samplelibrary --config {{ DEV_CONFIG }} reset --confirm; fi
    rm -rf dev-library

[group("dev")]
[windows]
dev-reset:
    if (Test-Path {{ DEV_CONFIG }}) { uv run samplelibrary --config {{ DEV_CONFIG }} reset --confirm }
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
[working-directory("frontend")]
frontend-types:
    uv run samplelibrary schema --output openapi.json
    uv run samplelibrary setup-schema --output setup-openapi.json
    npm run types

[group("release")]
package trackmod:
    npm --prefix frontend run build
    uv build --wheel --out-dir dist
    uv build --wheel --project trackmod --out-dir dist
    uv run python scripts/app_requirements.py --output dist/app-requirements.txt --trackmod "{{ trackmod }}"

[group("release")]
executable *arguments:
    uv run python scripts/build_app.py --dist dist {{ arguments }}

[group("release")]
publish-trackmod:
    uv build --project trackmod --out-dir dist/trackmod
    uv publish dist/trackmod/*

[group("docker")]
docker-build:
    docker build -t samplelibrary-server .

LIBRARY_MOUNT := "type=bind,target=/library,readonly,source="
CONFIG_MOUNT := "type=bind,target=/app/config.toml,readonly,source="

# Both paths are read from where the recipe was run, and a mount of a path that is not there fails
# rather than leaving an empty directory in its place.
[group("docker")]
[linux]
docker-run library_root config_path:
    docker run --rm --network host --mount "{{ LIBRARY_MOUNT }}{{ absolute_path(join(invocation_directory(), library_root)) }}" --mount "{{ CONFIG_MOUNT }}{{ absolute_path(join(invocation_directory(), config_path)) }}" samplelibrary-server serve --host 127.0.0.1 --port 8000

[group("docker")]
[macos]
[windows]
docker-run library_root config_path:
    docker run --rm -p 127.0.0.1:8000:8000 --mount "{{ LIBRARY_MOUNT }}{{ absolute_path(join(invocation_directory(), library_root)) }}" --mount "{{ CONFIG_MOUNT }}{{ absolute_path(join(invocation_directory(), config_path)) }}" samplelibrary-server
