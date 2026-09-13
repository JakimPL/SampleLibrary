set minimum-version := "1.56.0"
set default-list := true

[windows]
set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

MEMORY_CAP := "16G"
DEV_CONFIG := "dev-library/config.toml"
DEV_PORT := "8001"
CAPPED_SAMPLELIBRARY := if os() == "linux" { "systemd-run --user --scope -p MemoryMax=" + MEMORY_CAP + " -p MemorySwapMax=0 -q -- uv run samplelibrary" } else { "uv run samplelibrary" }

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
coverage:
    uv run pytest --cov --cov-report=term-missing

[group("quality")]
check: format lint test frontend-check

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
rebuild:
    {{ CAPPED_SAMPLELIBRARY }} extract
    {{ CAPPED_SAMPLELIBRARY }} notes
    {{ CAPPED_SAMPLELIBRARY }} thumbnails
    {{ CAPPED_SAMPLELIBRARY }} cloud embed
    {{ CAPPED_SAMPLELIBRARY }} cloud placeholders

[group("library")]
[linux]
[positional-arguments]
capped *arguments:
    {{ CAPPED_SAMPLELIBRARY }} "$@"

[group("library")]
reset: && _reset-confirmed
    uv run samplelibrary reset

[confirm("Empty the library named above?")]
_reset-confirmed:
    uv run samplelibrary reset --confirm

[group("dev")]
dev-build:
    uv run python scripts/build_dev_library.py

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
dev-reset: dev-build && _delete-dev-library
    uv run samplelibrary --config {{ DEV_CONFIG }} reset --confirm

[unix]
_delete-dev-library:
    rm -rf dev-library

[windows]
_delete-dev-library:
    Remove-Item -Recurse -Force dev-library

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
    npm run types

[group("docker")]
docker-build:
    docker build -t samplelibrary-server .

[group("docker")]
[linux]
docker-run library_root config_path:
    docker run --rm --network host -v "{{ absolute_path(library_root) }}:/library:ro" -v "{{ absolute_path(config_path) }}:/app/config.toml:ro" samplelibrary-server serve --host 127.0.0.1 --port 8000

[group("docker")]
[macos]
[windows]
docker-run library_root config_path:
    docker run --rm -p 127.0.0.1:8000:8000 -v "{{ absolute_path(library_root) }}:/library:ro" -v "{{ absolute_path(config_path) }}:/app/config.toml:ro" samplelibrary-server
