# syntax=docker/dockerfile:1

FROM node:26-bookworm-slim AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --extra server --extra morph --no-dev --no-editable --frozen --no-install-project
COPY README.md hatch_build.py ./
COPY src ./src
RUN uv sync --extra server --extra morph --no-dev --no-editable --frozen

FROM python:3.13-slim-bookworm AS runtime

RUN useradd --create-home --uid 1000 samplelibrary
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=frontend /build/frontend /app/frontend
COPY docker/site.toml /app/config.toml
ENV PATH="/app/.venv/bin:${PATH}" \
    SAMPLELIBRARY_CONFIG=/app/config.toml \
    SAMPLELIBRARY_FRONTEND_DIRECTORY=/app/frontend \
    WEB_CONCURRENCY=1 \
    NUMBA_CACHE_DIR=/tmp/numba \
    PYTHONUNBUFFERED=1
USER samplelibrary

# A healthy site is one whose catalog answers, on the port the platform names.
HEALTHCHECK CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/api/health\", timeout=5)"]
ENTRYPOINT ["samplelibrary"]
CMD ["site", "--host", "0.0.0.0"]
