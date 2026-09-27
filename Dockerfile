FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/venv UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
RUN mkdir -p backend/app && touch backend/app/__init__.py && uv sync --frozen --all-packages
WORKDIR /app/backend

# local development: code is mounted in by docker-compose.yml
FROM base AS dev
CMD ["sh", "-c", "uv sync --all-packages && uv run uvicorn app.main:app --host 0.0.0.0 --reload"]
