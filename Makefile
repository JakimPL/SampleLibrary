.PHONY: install
install:
	uv sync --all-extras --all-groups
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push
	$(MAKE) frontend-install

.PHONY: format
format:
	uv run isort src tests scripts
	uv run black src tests scripts

.PHONY: lint
lint:
	uv run mypy
	uv run pylint src scripts
	uv run lint-imports

.PHONY: test
test:
	uv run pytest -n auto

.PHONY: coverage
coverage:
	uv run pytest --cov --cov-report=term-missing

.PHONY: check
check: format lint test frontend-check

.PHONY: extract
extract:
	uv run sampleextract

.PHONY: equivalence
equivalence:
	uv run sampleequivalence

.PHONY: thumbnails
thumbnails:
	uv run samplethumbnail

.PHONY: embed
embed:
	uv run samplecloud

.PHONY: embed-modules-placeholder
embed-modules-placeholder:
	uv run samplecloud-modules-placeholder

# Destructive: empties the configured library's catalog and content store. Prints what it would
# do and changes nothing unless invoked as `make reset-library CONFIRM=1`.
.PHONY: reset-library
reset-library:
	uv run python scripts/reset_library.py $(if $(CONFIRM),--confirm,)


# The full pipeline in one command, in the order a rebuild needs: extraction before equivalence
# detection and embedding both depend on it, embedding's own coordinates are independent of
# equivalence detection's relations but placed after it here just to keep one linear read order.
.PHONY: rebuild-library
rebuild-library: extract equivalence embed embed-modules-placeholder

.PHONY: library-dev
library-dev:
	uv run python scripts/build_dev_library.py

.PHONY: extract-dev
extract-dev: library-dev
	SAMPLELIBRARY_CONFIG=dev-library/config.toml uv run sampleextract

.PHONY: equivalence-dev
equivalence-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml uv run sampleequivalence

.PHONY: embed-dev
embed-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml uv run samplecloud
	SAMPLELIBRARY_CONFIG=dev-library/config.toml uv run samplecloud-modules-placeholder

.PHONY: thumbnails-dev
thumbnails-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml uv run samplethumbnail

.PHONY: reset-dev
reset-dev:
	rm -rf dev-library

.PHONY: serve-dev
serve-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml uv run uvicorn sampleserver.main:app --reload --port 8001

.PHONY: serve
serve:
	uv run uvicorn sampleserver.main:app --reload

.PHONY: docker-build
docker-build:
	docker build -t samplelibrary-server .

# LIBRARY_ROOT and CONFIG_PATH must be set to your own local library directory and config.toml --
# see docs/architecture.md's Deployment section for the concurrency rule this container's own
# batch-job-timing convention comes from before running this alongside sampleextract/samplecloud.
.PHONY: docker-run
docker-run:
	docker run --rm -p 8000:8000 \
		-v "$(LIBRARY_ROOT)":/library \
		-v "$(CONFIG_PATH)":/app/config.toml \
		-e SAMPLELIBRARY_CONFIG=/app/config.toml \
		samplelibrary-server

.PHONY: openapi
openapi:
	uv run sampleserver-schema > frontend/openapi.json

.PHONY: frontend-types
frontend-types: openapi
	cd frontend && npm run types

.PHONY: frontend-install
frontend-install:
	cd frontend && npm install

.PHONY: frontend-dev
frontend-dev:
	cd frontend && npm run dev

.PHONY: frontend-build
frontend-build:
	cd frontend && npm run build

.PHONY: frontend-check
frontend-check:
	cd frontend && npm run typecheck && npm run lint && npm run format:check && npm test
