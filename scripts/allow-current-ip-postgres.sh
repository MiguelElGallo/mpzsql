#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

if ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI (az) is not installed."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "Azure CLI (az) is not authenticated; run az login first."
  exit 1
fi

if command -v azd >/dev/null 2>&1; then
  # Load only the non-secret azd values needed for this firewall rule.
  while IFS= read -r line; do
    [[ -z "${line}" ]] && continue
    line="${line#export }"
    [[ "${line}" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    value="${value#\"}"
    value="${value%\"}"
    case "${key}" in
      AZURE_RESOURCE_GROUP)
        [[ -z "${AZURE_RESOURCE_GROUP:-}" ]] && AZURE_RESOURCE_GROUP="${value}"
        ;;
      POSTGRES_SERVER_NAME)
        [[ -z "${POSTGRES_SERVER_NAME:-}" ]] && POSTGRES_SERVER_NAME="${value}"
        ;;
    esac
  done < <(cd "${repo_root}" && azd env get-values)
fi

required_vars=(
  AZURE_RESOURCE_GROUP
  POSTGRES_SERVER_NAME
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing ${var_name}; set it or run this from an azd environment."
    exit 1
  fi
done

rule_name="${FIREWALL_RULE_NAME:-AllowCurrentClientIpForTests}"
current_ip="${CURRENT_IP:-}"
if [[ -z "${current_ip}" ]]; then
  current_ip="$(curl -fsS https://api.ipify.org)"
fi

if [[ -z "${current_ip}" ]]; then
  echo "Could not detect current public IP; set CURRENT_IP to override."
  exit 1
fi

echo "Allowing current IP ${current_ip} on PostgreSQL server ${POSTGRES_SERVER_NAME}."

if az postgres flexible-server firewall-rule show \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --name "${POSTGRES_SERVER_NAME}" \
  --rule-name "${rule_name}" \
  --only-show-errors >/dev/null 2>&1; then
  az postgres flexible-server firewall-rule update \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_SERVER_NAME}" \
    --rule-name "${rule_name}" \
    --start-ip-address "${current_ip}" \
    --end-ip-address "${current_ip}" \
    --only-show-errors \
    --output none
else
  az postgres flexible-server firewall-rule create \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_SERVER_NAME}" \
    --rule-name "${rule_name}" \
    --start-ip-address "${current_ip}" \
    --end-ip-address "${current_ip}" \
    --only-show-errors \
    --output none
fi

echo "Firewall rule ${rule_name} now allows ${current_ip}."
