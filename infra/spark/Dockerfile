# syntax=docker/dockerfile:1.7
# ── Stage 0: Base ─────────────────────────────────────────────────────────────
# Apache Spark 4.1.1 official image (Ubuntu 22.04, Java 21, gosu pre-installed)
# spark user UID 185 and SPARK_HOME=/opt/spark already configured.
FROM apache/spark:4.1.1 AS base

USER root

# Retry transient apt/PPA network failures (Connection refused on launchpad CDN)
RUN echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::http::Timeout "30";' >> /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::https::Timeout "30";' >> /etc/apt/apt.conf.d/80-retries

# Install Python 3.12 via deadsnakes PPA (Ubuntu 22.04 ships 3.10 only)
# apt cache mount speeds up repeated builds without bloating the image layer
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends software-properties-common ca-certificates && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv && \
    python3.12 -m ensurepip --upgrade

RUN --mount=type=cache,target=/root/.cache/pip \
    python3.12 -m pip install --upgrade pip setuptools wheel

ENV PYSPARK_PYTHON=/usr/bin/python3.12 \
    PYSPARK_DRIVER_PYTHON=/usr/bin/python3.12 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── Stage 1: Python dependencies ──────────────────────────────────────────────
FROM base AS deps

COPY processing/spark/requirements.txt /tmp/spark-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3.12 -m pip install -r /tmp/spark-requirements.txt

# Pre-compile bytecode for faster executor startup
RUN python3.12 -m compileall -q /usr/local/lib/python3.12 2>/dev/null || true

# ── Stage 2: Cluster runtime (spark-master + spark-worker) ────────────────────
# target: cluster
# Bakes shared/ so executor-side imports resolve without --py-files.
FROM deps AS cluster

COPY --chown=185:185 shared/ /opt/spark/jobs/shared/

ENV PYTHONPATH=/opt/spark/jobs

USER 185

# ── Stage 3: Submit / standalone image (driver + job entry points) ─────────────
FROM cluster AS submit

USER root
COPY --chown=185:185 processing/spark/ /opt/spark/jobs/processing/spark/
USER 185
