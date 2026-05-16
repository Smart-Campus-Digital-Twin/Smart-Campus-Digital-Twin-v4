#!/usr/bin/env bash
# Apply Kubernetes secrets for the campus namespace from local env/*.env files.
#
# Usage:
#   bash deployment/k8s/apply-secrets.sh
#
# Requires:
#   - kubectl context pointing at the target cluster
#   - env/*.env files populated with real values (do not commit these)
#
# Secrets created match what manifests reference via secretRef / secretKeyRef.
# Each call is idempotent: --dry-run=client + kubectl apply -f -.

set -euo pipefail

NS="${NS:-campus}"
ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../env" && pwd)"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

apply_secret() {
  local name="$1"
  local env_file="$2"
  shift 2
  local keys=("$@")

  if [[ ! -f "$env_file" ]]; then
    echo "Skipping $name: $env_file missing"
    return
  fi

  local args=()
  for key in "${keys[@]}"; do
    local val
    val=$(grep -E "^${key}=" "$env_file" | head -n1 | cut -d= -f2- || true)
    if [[ -z "$val" ]]; then
      echo "Skipping $name: key $key absent in $env_file" >&2
      return
    fi
    args+=("--from-literal=${key}=${val}")
  done

  kubectl create secret generic "$name" \
    --namespace="$NS" \
    "${args[@]}" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "Applied secret $name"
}

# campus-postgres / postgres-env
apply_secret campus-postgres "$ENV_DIR/postgres.env" \
  POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD

apply_secret postgres-env "$ENV_DIR/postgres.env" \
  POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD DATABASE_URL

# campus-influxdb / influxdb-env
apply_secret campus-influxdb "$ENV_DIR/influxdb.env" \
  DOCKER_INFLUXDB_INIT_MODE \
  DOCKER_INFLUXDB_INIT_USERNAME \
  DOCKER_INFLUXDB_INIT_PASSWORD \
  DOCKER_INFLUXDB_INIT_ORG \
  DOCKER_INFLUXDB_INIT_BUCKET \
  DOCKER_INFLUXDB_INIT_ADMIN_TOKEN \
  INFLUXDB_TOKEN

apply_secret influxdb-env "$ENV_DIR/influxdb.env" \
  INFLUXDB_ORG INFLUXDB_TOKEN

# campus-keycloak / keycloak-env
apply_secret campus-keycloak "$ENV_DIR/keycloak.env" \
  KEYCLOAK_ADMIN KEYCLOAK_ADMIN_PASSWORD KC_DB_USERNAME KC_DB_PASSWORD

apply_secret keycloak-env "$ENV_DIR/keycloak.env" \
  KC_DB KC_DB_USERNAME KC_DB_PASSWORD KEYCLOAK_ADMIN KEYCLOAK_ADMIN_PASSWORD

# campus-mqtt (used by simulator, bridge, sim-control)
apply_secret campus-mqtt "$ENV_DIR/mosquitto.env" \
  MQTT_USERNAME MQTT_PASSWORD

# campus-grafana / grafana-env
apply_secret campus-grafana "$ENV_DIR/grafana.env" \
  GF_SECURITY_ADMIN_USER GF_SECURITY_ADMIN_PASSWORD

apply_secret grafana-env "$ENV_DIR/grafana.env" \
  GF_SECURITY_ADMIN_USER GF_SECURITY_ADMIN_PASSWORD

# api-env — manifest expects CORS_ORIGINS + JWT_SECRET_KEY.
# JWT_SECRET_KEY is not in api.env by default; supply via env or fall back.
JWT_SECRET_KEY_VAL="${JWT_SECRET_KEY:-changeme-jwt-secret-key-for-production}"
CORS_VAL=$(grep -E '^CORS_ORIGINS=' "$ENV_DIR/api.env" | head -n1 | cut -d= -f2-)
kubectl create secret generic api-env \
  --namespace="$NS" \
  --from-literal="CORS_ORIGINS=${CORS_VAL}" \
  --from-literal="JWT_SECRET_KEY=${JWT_SECRET_KEY_VAL}" \
  --dry-run=client -o yaml | kubectl apply -f -
echo "Applied secret api-env"

echo "All secrets applied to namespace $NS."
