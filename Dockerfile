FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/venv UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
COPY eval/pyproject.toml eval/
RUN mkdir -p backend/app eval/harness && touch backend/app/__init__.py eval/harness/__init__.py \
    && uv sync --frozen --all-packages
WORKDIR /app/backend

# local development: code is mounted in by docker-compose.yml
FROM base AS dev
CMD ["sh", "-c", "uv sync --all-packages && uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --reload"]

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# deploy: one container serving the API and the built frontend
FROM base AS prod
COPY backend/ /app/backend/
COPY eval/ /app/eval/
COPY data/ /app/data/
COPY --from=web /web/dist /app/web/dist
RUN uv sync --frozen --all-packages
ENV DATABASE_URL=sqlite:////data/coursecompass.db
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
