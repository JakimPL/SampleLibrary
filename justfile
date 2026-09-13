set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

MEMORY_CAP := "16G"
DEV_CONFIG := "dev-library/config.toml"
DEV_PORT := "8001"

# List every recipe.
default:
    @{{ just_executable() }} --list --unsorted

# Install the Python and frontend dependencies, the git hooks, and a config file to fill in.
[group("setup")]
install: && frontend-install
    uv sync --all-extras --all-groups
    uv run pre-commit install --hook-type pre-commit --hook-type pre-push
    uv run samplelibrary setup config

# Create the role and the databases the configuration names, wherever they are missing.
[group("setup")]
database:
    uv run samplelibrary setup database

# Sort imports and format the Python code.
[group("quality")]
format:
    uv run isort src tests scripts
    uv run black src tests scripts

# Check spelling, types, style and package boundaries.
[group("quality")]
lint:
    uv run codespell
    uv run mypy
    uv run pylint src scripts
    uv run lint-imports

# Run the Python tests, a process per core.
[group("quality")]
test:
    uv run pytest -n auto

# Run the Python tests with a report of the lines they leave unrun.
[group("quality")]
coverage:
    uv run pytest --cov --cov-report=term-missing

# Format, lint and test both the Python code and the frontend.
[group("quality")]
check: format lint test frontend-check

# Serve the API, restarting it whenever the code changes.
[group("library")]
serve:
    uv run samplelibrary serve --reload

# Serve morphs to the API from the models under the library root.
[group("library")]
serve-inference:
    uv run samplelibrary morph serve

# Browse the runs every training and evaluation pass recorded.
[group("library")]
tracking-ui:
    uv run mlflow ui --backend-store-uri "$(uv run samplelibrary tracking uri)"

# Rebuild the catalog and the cloud from the configured modules.
[group("library")]
rebuild:
    uv run samplelibrary extract
    uv run samplelibrary equivalence
    uv run samplelibrary cloud embed
    uv run samplelibrary cloud placeholders

# Run a samplelibrary command under a memory ceiling, with swap closed to it.
[group("library")]
[linux]
[positional-arguments]
capped *arguments:
    systemd-run --user --scope -p MemoryMax={{ MEMORY_CAP }} -p MemorySwapMax=0 -q -- uv run samplelibrary "$@"

# Empty the configured library's catalog and content store; hand annotations stay.
[group("library")]
[confirm("Empty the configured library's catalog and content store for good?")]
reset:
    uv run samplelibrary reset --confirm

# Generate the 30-module sandbox and its config.
[group("dev")]
dev-build:
    uv run python scripts/build_dev_library.py

# Run a samplelibrary command on the sandbox.
[group("dev")]
[unix]
[positional-arguments]
dev *arguments:
    uv run samplelibrary --config {{ DEV_CONFIG }} "$@"

# Run a samplelibrary command on the sandbox.
[group("dev")]
[windows]
dev *arguments:
    uv run samplelibrary --config {{ DEV_CONFIG }} {{ arguments }}

# Serve the API over the sandbox, beside the one serving the library.
[group("dev")]
serve-dev:
    uv run samplelibrary --config {{ DEV_CONFIG }} serve --reload --port {{ DEV_PORT }}

# Delete the sandbox.
[group("dev")]
[unix]
dev-reset:
    rm -rf dev-library

# Delete the sandbox.
[group("dev")]
[windows]
dev-reset:
    if (Test-Path dev-library) { Remove-Item -Recurse -Force dev-library }

# Install the frontend's dependencies.
[group("frontend")]
[working-directory("frontend")]
frontend-install:
    npm install

# Start the frontend's development server, reachable from the local network.
[group("frontend")]
[working-directory("frontend")]
frontend-dev:
    npm run dev -- --host

# Build the frontend for production.
[group("frontend")]
[working-directory("frontend")]
frontend-build:
    npm run build

# Type-check, lint, format-check and test the frontend.
[group("frontend")]
[working-directory("frontend")]
frontend-check:
    npm run typecheck
    npm run lint
    npm run format:check
    npm test

# Export the API's schema and generate the frontend's types from it.
[group("frontend")]
[working-directory("frontend")]
frontend-types:
    uv run samplelibrary schema --output openapi.json
    npm run types

# Build the API's image.
[group("docker")]
docker-build:
    docker build -t samplelibrary-server .

# Run the API's image over a library directory and the config that describes it inside the container.
[group("docker")]
docker-run library_root config_path:
    docker run --rm -p 8000:8000 -v "{{ library_root }}:/library" -v "{{ config_path }}:/app/config.toml" -e SAMPLELIBRARY_CONFIG=/app/config.toml samplelibrary-server
