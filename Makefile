.PHONY: install
install:
	uv sync --all-extras --all-groups
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push
	$(MAKE) frontend-install

.PHONY: format
format:
	uv run isort src tests
	uv run black src tests

.PHONY: lint
lint:
	uv run mypy
	uv run pylint src
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

.PHONY: serve
serve:
	uv run uvicorn sampleserver.main:app --reload

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
