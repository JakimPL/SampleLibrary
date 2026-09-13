# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY trackmod ./trackmod
COPY src ./src

# Real wheels, trackmod included, let the runtime stage carry the venv alone.
RUN uv sync --extra server --no-dev --no-editable --frozen

FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000
ENTRYPOINT ["samplelibrary", "serve", "--host", "0.0.0.0", "--port", "8000"]
CMD ["--workers", "4"]
