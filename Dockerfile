# syntax=docker/dockerfile:1

# Builds a runtime image for sampleserver's read-only API alone. The offline batch pipelines
# (sampleextract, samplecloud) never run in this container -- see docs/architecture.md's
# "Deployment" section for why those stay separate, single-writer jobs run outside it.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY trackmod ./trackmod
COPY src ./src

# The `server` extra pulls in only fastapi/uvicorn; sampleextract/samplecloud's own heavier
# dependencies (librosa, umap-learn, scikit-learn), gated behind the `cloud` extra, are never
# installed here -- mirroring the import-linter boundary that already keeps sampleserver from
# importing either offline pipeline package in code. `--no-editable` builds real wheels (this
# project's four packages, plus the local `trackmod` path dependency) into the venv, so the
# runtime stage below needs nothing from `/app/src` -- only the venv itself.
RUN uv sync --extra server --no-dev --no-editable --frozen

FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

# library_root, module_source_directory, and a config.toml pointing at their in-container paths
# are supplied at `docker run` time (a bind mount plus SAMPLELIBRARY_CONFIG) -- deployment-specific
# paths stay out of the image, matching this project's config.toml already never being committed.
EXPOSE 8000
ENTRYPOINT ["uvicorn", "sampleserver.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["--workers", "4"]
