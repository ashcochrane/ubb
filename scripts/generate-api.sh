#!/bin/bash
# Generates TypeScript types from django-ninja OpenAPI schemas.
# Requires the Django dev server running on localhost:8000.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$SCRIPT_DIR/../src/api/generated"
mkdir -p "$OUT_DIR"

BASE_URL="${API_URL:-http://localhost:8000}"

APIS=("platform" "metering" "billing" "tenant")

for api in "${APIS[@]}"; do
  echo "Generating types for $api..."
  url="$BASE_URL/api/v1/$api/openapi.json"
  npx openapi-typescript "$url" -o "$OUT_DIR/${api}.ts"
done

echo "Done! Generated types for: ${APIS[*]}"
