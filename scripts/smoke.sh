#!/usr/bin/env bash
set -euo pipefail
url="$(tofu -chdir=deployment/gcp output -raw service_url)"
token="$(gcloud auth print-identity-token)"
curl --fail --silent --show-error "$url/v1/answers" -H "Authorization: Bearer $token" -H "Content-Type: application/json" -d '{"query":"Which brake pads fit Aster Compact 2022?","request_id":"smoke-1"}'
