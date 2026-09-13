set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

MEMORY_CAP := "16G"
DEV_CONFIG := "dev-library/config.toml"
DEV_PORT := "8001"

default:
    @{{ just_executable() }} --list --unsorted

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
    uv run isort src tests scripts
    uv run black src tests scripts

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
    uv run mlflow ui --backend-store-uri "$(uv run samplelibrary tracking uri)"

[group("library")]
rebuild:
    uv run samplelibrary extract
    uv run samplelibrary equivalence
    uv run samplelibrary cloud embed
    uv run samplelibrary cloud placeholders

[group("library")]
[linux]
[positional-arguments]
capped *arguments:
    systemd-run --user --scope -p MemoryMax={{ MEMORY_CAP }} -p MemorySwapMax=0 -q -- uv run samplelibrary "$@"

[group("library")]
[confirm("Empty the configured library's catalog and content store for good?")]
reset:
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
dev *arguments:
    uv run samplelibrary --config {{ DEV_CONFIG }} {{ arguments }}

[group("dev")]
serve-dev:
    uv run samplelibrary --config {{ DEV_CONFIG }} serve --reload --port {{ DEV_PORT }}

[group("dev")]
[unix]
dev-reset:
    rm -rf dev-library

[group("dev")]
[windows]
dev-reset:
    if (Test-Path dev-library) { Remove-Item -Recurse -Force dev-library }

[group("frontend")]
[working-directory("frontend")]
frontend-install:
    npm install

[group("frontend")]
[working-directory("frontend")]
frontend-dev:
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
    npm run types

[group("docker")]
docker-build:
    docker build -t samplelibrary-server .

[group("docker")]
docker-run library_root config_path:
    docker run --rm -p 8000:8000 -v "{{ library_root }}:/library" -v "{{ config_path }}:/app/config.toml" -e SAMPLELIBRARY_CONFIG=/app/config.toml samplelibrary-server
