#!/usr/bin/env bash
set -euo pipefail

# Homebrew installs libpq as keg-only, so add it explicitly when present.
if [[ -d "/opt/homebrew/opt/libpq/bin" ]]; then
  export PATH="/opt/homebrew/opt/libpq/bin:${PATH}"
fi

if ! command -v az >/dev/null 2>&1; then
  echo "Skipping postprovision PostgreSQL grants: az CLI is not installed."
  exit 0
fi

if ! az account show >/dev/null 2>&1; then
  echo "Skipping postprovision PostgreSQL grants: az CLI is not authenticated."
  exit 0
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "Skipping postprovision PostgreSQL grants: psql is not installed."
  exit 0
fi

if command -v azd >/dev/null 2>&1; then
  # Ensure latest azd environment variables (including Bicep outputs) are loaded.
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    value="${value#\"}"
    value="${value%\"}"
    export "${key}=${value}"
  done < <(azd env get-values)
fi

required_vars=(
  AZURE_RESOURCE_GROUP
  POSTGRES_SERVER_NAME
  POSTGRES_FQDN
  POSTGRES_DATABASE_NAME
  POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME
  CONTAINER_APP_IDENTITY_NAME
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Skipping postprovision PostgreSQL grants: missing ${var_name}."
    exit 0
  fi
done

cleanup_firewall_rule() {
  if [[ -n "${created_firewall_rule:-}" ]]; then
    az postgres flexible-server firewall-rule delete \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --name "${POSTGRES_SERVER_NAME}" \
      --rule-name "AllowCurrentClientIp" \
      --only-show-errors \
      --yes >/dev/null 2>&1 || true
  fi
}
trap cleanup_firewall_rule EXIT

current_ip="${CURRENT_IP:-}"
if [[ -z "${current_ip}" ]]; then
  current_ip="$(curl -fsS https://api.ipify.org || true)"
fi
if [[ -n "${current_ip}" ]]; then
  az postgres flexible-server firewall-rule create \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_SERVER_NAME}" \
    --rule-name "AllowCurrentClientIp" \
    --start-ip-address "${current_ip}" \
    --end-ip-address "${current_ip}" \
    --only-show-errors >/dev/null
  created_firewall_rule=1
else
  echo "Could not auto-detect public IP (set CURRENT_IP to override); continuing without temporary firewall rule."
fi

# ── Wait for PostgreSQL Entra AAD subsystem to become ready ──────────────
# After a fresh provision the AAD subsystem can take several minutes to
# initialise.  We retry a simple SELECT 1 via psql up to 12 times (≈5 min)
# before giving up.
max_retries=12
retry_interval=25
echo "Waiting for PostgreSQL Entra auth to become ready (up to $((max_retries * retry_interval))s) ..."
for attempt in $(seq 1 ${max_retries}); do
  access_token="$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)"
  if PGPASSWORD="${access_token}" \
    psql "host=${POSTGRES_FQDN} port=5432 dbname=postgres sslmode=require connect_timeout=10" \
      --username "${POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME}" \
      -c "SELECT 1" >/dev/null 2>&1; then
    echo "PostgreSQL is reachable (attempt ${attempt}/${max_retries})."
    break
  fi
  if [[ ${attempt} -eq ${max_retries} ]]; then
    echo "ERROR: PostgreSQL did not become reachable after $((max_retries * retry_interval))s."
    exit 1
  fi
  echo "  Attempt ${attempt}/${max_retries} failed — retrying in ${retry_interval}s …"
  sleep ${retry_interval}
done

# ── Apply grants ─────────────────────────────────────────────────────────
access_token="$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)"
PGPASSWORD="${access_token}" \
psql "host=${POSTGRES_FQDN} port=5432 dbname=postgres sslmode=require" \
  --username "${POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME}" \
  --set ON_ERROR_STOP=1 \
  --set app_database_name="${POSTGRES_DATABASE_NAME}" \
  --set app_identity_name="${CONTAINER_APP_IDENTITY_NAME}" \
  --file ./scripts/postgres-grants.sql

echo "PostgreSQL grants applied for identity ${CONTAINER_APP_IDENTITY_NAME}."
