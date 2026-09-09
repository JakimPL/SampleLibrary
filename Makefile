# npm picks its script shell from ComSpec, which make does not pass on, leaving cmd.exe to resolve
# commands from a POSIX PATH it cannot read: the script prints its banner and exits 1 having run
# nothing. Naming the shell make itself uses keeps these targets working, on Windows and elsewhere.
NPM := npm --script-shell=$(SHELL)

.PHONY: install
install:
	uv sync --all-extras --all-groups
	uv run pre-commit install --hook-type pre-commit --hook-type pre-push
	uv run python scripts/setup.py config
	$(MAKE) frontend-install

# Creates the role and the three databases this project expects, wherever they are missing, and
# leaves everything already on the server exactly as it is -- a catalog's rows and the `curation`
# schema's hand-made labels, ratings and favorites included. Safe to re-run at any time.
.PHONY: database
database:
	uv run python scripts/setup.py database

.PHONY: format
format:
	uv run isort src tests scripts
	uv run black src tests scripts

.PHONY: lint
lint:
	uv run codespell
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

# WORKERS is how many processes one run spends on the corpus: `make extract WORKERS=2`. Left
# unset, a run takes one per core, up to a ceiling one machine's memory carries comfortably.
.PHONY: extract
extract:
	uv run sampleextract $(if $(WORKERS),--workers $(WORKERS),)

.PHONY: equivalence
equivalence:
	uv run sampleequivalence

.PHONY: thumbnails
thumbnails:
	uv run samplethumbnail

.PHONY: notes
notes:
	uv run samplenotes

# Hand-made sample annotations. The export is the copy that outlives the database, and nothing else in
# this repository can rebuild one -- keep it somewhere safe of your own.
.PHONY: annotations-export
annotations-export:
	uv run sampleannotations export

.PHONY: annotations-import
annotations-import:
	uv run sampleannotations import

# Reattaches annotations whose sample hash the catalog no longer holds, through the module slot each was
# chosen from. Run it after anything that changes how samples are hashed.
.PHONY: annotations-relink
annotations-relink:
	uv run sampleannotations relink

.PHONY: embed
embed:
	uv run samplecloud

.PHONY: embed-modules-placeholder
embed-modules-placeholder:
	uv run samplecloud-modules-placeholder

# Scores one experiment's descriptor against the catalog's own targets. EXPERIMENT is the
# experiment id; OUTPUT, when given, writes the report as JSON. Transposition retrieval reads and
# describes audio again, so `evaluate-fast` leaves it out for a pass over the stored vectors alone.
.PHONY: evaluate
evaluate:
	uv run samplecloud-evaluate --experiment-id $(EXPERIMENT) $(if $(PROBES),--probes $(PROBES),) $(if $(OUTPUT),--output $(OUTPUT),)

.PHONY: evaluate-fast
evaluate-fast:
	uv run samplecloud-evaluate --experiment-id $(EXPERIMENT) --skip-transposition $(if $(OUTPUT),--output $(OUTPUT),)

# The decodable representation. `morph-fit` learns a codec over a draw of the library and writes it
# under the configured library root; `morph-render` writes a listening set between two sample
# hashes. FIRST and SECOND are hashes from the real library: the dev sandbox has no counterpart
# here on purpose, since its 40-100 ms synthetic tones say nothing about how a morph sounds.
.PHONY: morph-fit
morph-fit:
	uv run samplemorph fit $(if $(CANONICALIZER),--canonicalizer $(CANONICALIZER),) $(if $(LATENT),--latent-size $(LATENT),)

# Teaches a phase model on the magnitudes the canonicalizer produces and writes it under the library
# root. SAMPLES and EPOCHS size the run; the pass reads audio in worker processes and trains on the
# GPU, so its length follows the sample count times the epoch count.
.PHONY: morph-train-phase
morph-train-phase:
	uv run samplemorph train-phase $(if $(SAMPLES),--samples $(SAMPLES),) $(if $(EPOCHS),--epochs $(EPOCHS),) $(if $(PHASE_MODEL),--phase-model $(PHASE_MODEL),)

.PHONY: morph-render
morph-render:
	uv run samplemorph render --first $(FIRST) --second $(SECOND) --output $(OUTPUT)

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

# dev-library keeps its own database on the same local Postgres server the real library uses, so a
# rebuild of this disposable 30-module sandbox leaves the real catalog untouched. `make database`
# creates that database, along with the role and the two others this project expects.
DEV_DATABASE_URL := postgresql+psycopg://samplelibrary:samplelibrary@localhost:5432/samplelibrary_dev

.PHONY: library-dev
library-dev:
	uv run python scripts/build_dev_library.py

.PHONY: extract-dev
extract-dev: library-dev
	SAMPLELIBRARY_CONFIG=dev-library/config.toml SAMPLELIBRARY_DATABASE_URL=$(DEV_DATABASE_URL) uv run sampleextract $(if $(WORKERS),--workers $(WORKERS),)

.PHONY: equivalence-dev
equivalence-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml SAMPLELIBRARY_DATABASE_URL=$(DEV_DATABASE_URL) uv run sampleequivalence

.PHONY: embed-dev
embed-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml SAMPLELIBRARY_DATABASE_URL=$(DEV_DATABASE_URL) uv run samplecloud
	SAMPLELIBRARY_CONFIG=dev-library/config.toml SAMPLELIBRARY_DATABASE_URL=$(DEV_DATABASE_URL) uv run samplecloud-modules-placeholder

.PHONY: thumbnails-dev
thumbnails-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml SAMPLELIBRARY_DATABASE_URL=$(DEV_DATABASE_URL) uv run samplethumbnail

.PHONY: notes-dev
notes-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml SAMPLELIBRARY_DATABASE_URL=$(DEV_DATABASE_URL) uv run samplenotes

.PHONY: reset-dev
reset-dev:
	rm -rf dev-library

.PHONY: serve-dev
serve-dev:
	SAMPLELIBRARY_CONFIG=dev-library/config.toml SAMPLELIBRARY_DATABASE_URL=$(DEV_DATABASE_URL) uv run uvicorn sampleserver.main:app --reload --port 8001

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
	cd frontend && $(NPM) run types

.PHONY: frontend-install
frontend-install:
	cd frontend && $(NPM) install

.PHONY: frontend-dev
frontend-dev:
	cd frontend && $(NPM) run dev

.PHONY: frontend-build
frontend-build:
	cd frontend && $(NPM) run build

.PHONY: frontend-check
frontend-check:
	cd frontend && $(NPM) run typecheck && $(NPM) run lint && $(NPM) run format:check && $(NPM) test
