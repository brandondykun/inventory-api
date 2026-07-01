# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Multi-stage build using uv. Targets:
#   dev  -> includes dev dependency group, source bind-mounted by compose
#   prod -> slim runtime, production deps only, runs gunicorn
# ---------------------------------------------------------------------------
ARG PYTHON_VERSION=3.13

FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Runtime libs: libpq for Postgres, curl for healthchecks/wait loops.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Non-root runtime user.
RUN groupadd --system app && useradd --system --gid app --create-home app

COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# --- production dependencies (no dev group, no project) --------------------
FROM base AS deps-prod
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# --- development dependencies (includes dev group) ------------------------
FROM base AS deps-dev
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# ===========================================================================
# Development image
# ===========================================================================
FROM base AS dev
COPY --from=deps-dev /opt/venv /opt/venv
COPY . .
RUN chown -R app:app /app
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ===========================================================================
# Production image
# ===========================================================================
FROM base AS prod
COPY --from=deps-prod /opt/venv /opt/venv
COPY . .
# staticfiles/mediafiles are written at runtime — ensure the app user owns them.
RUN mkdir -p /app/staticfiles /app/mediafiles && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
