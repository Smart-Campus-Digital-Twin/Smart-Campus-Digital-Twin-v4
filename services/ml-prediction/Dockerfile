# syntax=docker/dockerfile:1.7
# ── Stage 1: shared system base ───────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends libpq5

RUN addgroup --system --gid 1001 appgroup && \
    adduser  --system --uid 1001 --ingroup appgroup appuser

WORKDIR /opt/campus

# ── Stage 2: Python dependency builder ────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY ml/requirements.txt /tmp/ml-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/ml-requirements.txt \
    && pip install "setuptools>=65.0,<72"

# Pre-compile bytecode — exclude cookiecutter templates (invalid Python syntax)
RUN python -m compileall -q -x 'cookiecutter' /venv/lib || true

# ── Stage 3: training runtime ─────────────────────────────────────────────────
# Used by campus-ml-training. Sleeps until Airflow exec-s a kedro run into it,
# or bootstrap_training.py is run manually once to seed MLflow.
FROM base AS training

COPY --from=builder --chown=appuser:appgroup /venv /venv

COPY --chown=appuser:appgroup ml/       ./ml/
COPY --chown=appuser:appgroup shared/   ./shared/

ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/opt/campus \
    KEDRO_DISABLE_TELEMETRY=true \
    PYTHONWARNINGS=ignore

USER appuser
CMD ["sleep", "infinity"]

# ── Stage 4: inference runtime ────────────────────────────────────────────────
# Used by campus-ml-inference. Sleeps until Airflow exec-s the batch inference
# script into it on schedule.
FROM base AS inference

COPY --from=builder --chown=appuser:appgroup /venv /venv

COPY --chown=appuser:appgroup ml/       ./ml/
COPY --chown=appuser:appgroup shared/   ./shared/

ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/opt/campus \
    MLFLOW_TRACKING_URI=http://mlflow:5000

USER appuser
CMD ["sleep", "infinity"]
