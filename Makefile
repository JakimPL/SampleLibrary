.PHONY: install
install:
	uv sync --all-extras --all-groups
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push

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
check: format lint test

.PHONY: extract
extract:
	uv run sampleextract

.PHONY: equivalence
equivalence:
	uv run sampleequivalence

.PHONY: serve
serve:
	uv run uvicorn sampleserver.main:app --reload
