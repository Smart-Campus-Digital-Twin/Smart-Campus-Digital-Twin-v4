#!/bin/bash
# InfluxDB 2.x bootstrap — creates org, buckets, and API token on first run.
#
# Run once after the InfluxDB container is healthy:
#   docker compose exec influxdb /influxdb-setup/setup.sh
# Or mount this as the entrypoint for the influxdb-init one-shot container.
set -euo pipefail

# InfluxDB 2.x CLI reads connection config from environment variables.
export INFLUX_HOST="${INFLUXDB_URL:-http://influxdb:8086}"
export INFLUX_TOKEN="${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}"
export INFLUX_ORG="${INFLUXDB_ORG:-smart-campus}"

echo "==> Waiting for InfluxDB to be ready..."
# Use 'influx ping' (available in the influxdb image) — curl is NOT in influxdb:2.7
until influx ping --host "${INFLUX_HOST}" > /dev/null 2>&1; do
    echo "    InfluxDB not ready yet — retrying in 3s..."
    sleep 3
done
echo "==> InfluxDB is ready."

# ------------------------------------------------------------------
# Buckets — one per retention tier
# ------------------------------------------------------------------
# campus_raw  : 7 days  — raw readings, written by ml-consumer at ~1-sec latency
# campus_1m   : 30 days — 1-min aggregations, written by ml-consumer rollup task
# campus_1h   : 1 year  — 1-hour roll-ups, written by Flux task (downsample_1m_to_1h)
# campus_1d   : 5 years — daily roll-ups, written by Flux task (downsample_1h_to_1d)
# ------------------------------------------------------------------

for BUCKET in "campus_raw:168h" "campus_1m:720h" "campus_1h:8760h" "campus_1d:43800h" "campus_predictions:8760h"; do
    NAME="${BUCKET%%:*}"
    RETENTION="${BUCKET##*:}"
    # Retry bucket check to handle transient connection errors
    RETRIES=5
    until influx bucket list --name "${NAME}" --host "${INFLUX_HOST}" > /dev/null 2>&1 || [ $RETRIES -eq 0 ]; do
        echo "    Retrying bucket check for '${NAME}'..."
        sleep 2
        RETRIES=$((RETRIES - 1))
    done
    if influx bucket list --name "${NAME}" --host "${INFLUX_HOST}" > /dev/null 2>&1; then
        echo "  Bucket '${NAME}' already exists — skipping."
    else
        influx bucket create \
            --name "${NAME}" \
            --retention "${RETENTION}" \
            --host "${INFLUX_HOST}"
        echo "  Created bucket '${NAME}' with retention ${RETENTION}."
    fi
done

# ------------------------------------------------------------------
# Flux tasks — register continuous downsampling tasks
# ------------------------------------------------------------------

for TASK_FILE in /influxdb-setup/tasks/*.flux; do
    if [ -f "${TASK_FILE}" ]; then
        TASK_NAME=$(basename "${TASK_FILE}" .flux)
        if influx task list --host "${INFLUX_HOST}" 2>/dev/null | grep -q "${TASK_NAME}"; then
            echo "  Task '${TASK_NAME}' already exists — skipping."
        else
            influx task create \
                --file "${TASK_FILE}" \
                --host "${INFLUX_HOST}"
            echo "  Created Flux task '${TASK_NAME}'."
        fi
    fi
done

echo "==> InfluxDB setup complete."
