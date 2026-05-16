# syntax=docker/dockerfile:1.7
# ── Stage 0: JDK headers ─────────────────────────────────────────────────────
# Provides include/ so pip can compile apache-flink's C extension on ARM64.
FROM eclipse-temurin:17-jdk-jammy AS jdk-headers

# ── Stage 1: Connector JARs ───────────────────────────────────────────────────
# Uses alpine (tiny) so curl never leaks into any flink image layer.
# All JARs sourced from Maven Central for consistent SHA-256 availability.
# JAR cache is invalidated only when URL ARGs change — never by Python deps.
FROM alpine:3.20 AS jars

RUN --mount=type=cache,target=/var/cache/apk \
    apk add --no-cache curl

RUN set -eux; \
    KAFKA_URL="https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.4.0-1.20/flink-sql-connector-kafka-3.4.0-1.20.jar"; \
    JDBC_URL="https://repo1.maven.org/maven2/org/apache/flink/flink-connector-jdbc/3.3.0-1.20/flink-connector-jdbc-3.3.0-1.20.jar"; \
    PG_URL="https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.3/postgresql-42.7.3.jar"; \
    mkdir /jars; \
    curl -fsSL "${KAFKA_URL}" -o /jars/kafka-connector.jar; \
    curl -fsSL "${JDBC_URL}" -o /jars/jdbc-connector.jar; \
    curl -fsSL "${PG_URL}" -o /jars/postgresql.jar

# ── Stage 2: Python runtime + dependencies ────────────────────────────────────
# Build tools are purged in the same RUN as pip install — zero build tools
# in the cluster or submit images.  Requirements cache is independent of JARs.
FROM flink:1.20-scala_2.12-java17 AS builder

COPY --from=jdk-headers /opt/java/openjdk/include /opt/java/openjdk/include
COPY --from=jars        /jars/                    /opt/flink/lib/

COPY processing/flink/requirements.txt /tmp/flink-requirements.txt

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
           python3.11 python3.11-dev python3-pip build-essential cmake \
    && ln -sf python3.11 /usr/bin/python3 \
    && ln -sf python3 /usr/bin/python \
    && chmod -R a+rX /opt/flink/conf

RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --upgrade pip setuptools wheel \
    && pip3 install -r /tmp/flink-requirements.txt

RUN apt-get purge -y --auto-remove build-essential cmake python3.11-dev \
    && rm -rf /root/.cache /tmp/flink-requirements.txt

# Pre-compile bytecode → faster task startup
RUN python3.11 -m compileall -q /usr/local/lib/python3.11 2>/dev/null || true

# ── Stage 3: Flink cluster runtime (jobmanager + taskmanager) ─────────────────
# target: cluster
# Non-root: only the three dirs Flink actually writes to are chowned.
# Prometheus reporter in /opt/flink/plugins/metrics-prometheus/ is
# auto-discovered — enable via metrics.reporter.prom.* in FLINK_PROPERTIES.
FROM builder AS cluster

RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --ingroup appgroup appuser \
    && mkdir -p /opt/flink/log /opt/flink/pid /tmp/flink-logs \
    && chown appuser:appgroup /opt/flink/log /opt/flink/pid /tmp/flink-logs

ENV FLINK_LOG_DIR=/tmp/flink-logs \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser

# ── Stage 4: Job submit image ─────────────────────────────────────────────────
FROM cluster AS submit

WORKDIR /app
COPY --chown=appuser:appgroup shared/           ./shared/
COPY --chown=appuser:appgroup processing/flink/ ./processing/flink/

ENV PYTHONPATH=/app

CMD ["/bin/bash", "/app/processing/flink/submit.sh"]
