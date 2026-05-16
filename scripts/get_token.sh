#!/usr/bin/env bash
set -euo pipefail

# Dev helper: fetch Keycloak access token.
# Usage:
#   scripts/get_token.sh
#   KEYCLOAK_BASE_URL=http://localhost:8083 KEYCLOAK_REALM=campus \
#     KEYCLOAK_CLIENT_ID=campus-dev KEYCLOAK_USERNAME=dev KEYCLOAK_PASSWORD=dev \
#     scripts/get_token.sh

KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://localhost:8083}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-campus}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-campus-dev}"
KEYCLOAK_USERNAME="${KEYCLOAK_USERNAME:-dev}"
KEYCLOAK_PASSWORD="${KEYCLOAK_PASSWORD:-dev}"

TOKEN_URL="${KEYCLOAK_BASE_URL%/}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token"

json=$(curl -sfS \
  -X POST "$TOKEN_URL" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "grant_type=password" \
  --data-urlencode "client_id=${KEYCLOAK_CLIENT_ID}" \
  --data-urlencode "username=${KEYCLOAK_USERNAME}" \
  --data-urlencode "password=${KEYCLOAK_PASSWORD}")

python3 -c 'import json,sys; d=json.load(sys.stdin); t=d.get("access_token");\
    (sys.stdout.write(t) if t else (sys.stderr.write("No access_token in response\n"+json.dumps(d,indent=2)+"\n"), sys.exit(1)))' \
  <<<"$json"
