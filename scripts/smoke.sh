#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

url="$(tofu -chdir=deployment/gcp output -raw service_url)"
token="$(gcloud auth print-identity-token)"

echo "Testing Health endpoint (${url}/health)..."
curl --fail --silent --show-error "${url}/health" -H "Authorization: Bearer ${token}"
echo ""

echo "Testing Query Answers endpoint (${url}/v1/answers)..."
curl --fail --silent --show-error "${url}/v1/answers" \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/json" \
  -d '{"query":"Which brake pads fit Aster Compact 2022?","request_id":"smoke-1"}'
echo ""
