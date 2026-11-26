# syntax=docker/dockerfile:1
#
# EquiTask AI backend — multi-stage Dockerfile.
#
# Stage 1 "deps":   install Python dependencies into an isolated prefix.
# Stage 2 "runtime": slim image with only the installed package, the app code,
#                    and a non-root user. DRAFT — not hardened for production.
#

# ---- Build stage: dependencies ----
FROM python:3.13-slim AS deps
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml alembic.ini ./
RUN pip install --no-cache-dir --prefix=/install .

# ---- Run stage: application ----
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000
WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r equitask \
    && useradd -r -g equitask -s /usr/sbin/nologin -d /app equitask
COPY --from=deps /install /usr/local
COPY --chown=equitask:equitask app ./app
COPY --chown=equitask:equitask alembic ./alembic
COPY --chown=equitask:equitask pyproject.toml alembic.ini ./
USER equitask
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
