# syntax=docker/dockerfile:1.7

# ---------- builder ----------
# Installs uv, compiles/sync'd deps into /app/.venv.
FROM python:3.12-slim-bookworm AS builder

# Pin uv. Bump deliberately; do not float to `latest` in production.
COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build deps for any packages that need to compile (argon2, cryptography, psycopg bits).
# Kept minimal; removed from the final image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      libffi-dev \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cache layer independent of source).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Install the project itself (src/) without dev extras.
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.12-slim-bookworm AS runtime

# Minimal runtime libs: libpq for asyncpg fallbacks, curl for health probes,
# ca-certificates for outbound TLS (Deepgram, Anthropic, OpenAI, Stripe, Resend).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      libpq5 \
 && rm -rf /var/lib/apt/lists/*

# Non-root user.
RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

# Copy the pre-built venv and project source from the builder stage.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src ./src
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent --show-error "http://127.0.0.1:${PORT:-8000}/health/live" || exit 1

# Default to the API server. Worker and release process groups override CMD.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
