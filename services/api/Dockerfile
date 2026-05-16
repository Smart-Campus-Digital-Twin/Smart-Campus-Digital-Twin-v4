# syntax=docker/dockerfile:1.7
# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY api/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements.txt

# Pre-compile bytecode → faster container startup
RUN python -m compileall -q /venv/lib

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --ingroup appgroup appuser

COPY --from=builder --chown=appuser:appgroup /venv /venv

WORKDIR /app
COPY --chown=appuser:appgroup shared/ ./shared/
COPY --chown=appuser:appgroup api/ ./api/

ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
