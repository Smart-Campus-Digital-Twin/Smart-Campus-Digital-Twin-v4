#!/bin/bash
# Submits all three Flink jobs to the cluster once it is ready.
# Run inside the flink-submit container (see docker-compose.yml).
set -euo pipefail

MASTER="${FLINK_MASTER:-flink-jobmanager:8081}"
JOBS_DIR="/app/processing/flink/jobs"

wait_for_flink() {
    echo "Waiting for Flink cluster at ${MASTER}..."
    until curl -sf "http://${MASTER}/overview" | grep -q '"taskmanagers"'; do
        sleep 3
    done
    echo "Flink cluster is ready."
}

submit() {
    local job_module=$1
    echo "Submitting ${job_module}..."
    flink run \
        --jobmanager "${MASTER}" \
        --python "${JOBS_DIR}/${job_module}.py" \
        --pyFiles /app \
        &
}

wait_for_flink

submit kafka_to_influx
submit window_agg
submit anomaly
submit prediction

# Wait for all submissions to complete
wait
echo "All jobs submitted."
