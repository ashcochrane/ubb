#!/bin/bash
# Generates TypeScript types from the canonical Django Ninja OpenAPI schema.
#
# Two phases:
#   fetch    — pulls /api/v1/openapi.json into the one tracked local snapshot.
#   generate — runs openapi-typescript against that snapshot.
#
# Commit the snapshot, never generated declarations. The snapshot makes the
# contract reviewable in PRs and lets declarations be regenerated offline.
#
# Usage:
#   ./generate-api.sh fetch     # snapshots only (requires Django dev server)
#   ./generate-api.sh generate  # types only (works offline)
#   ./generate-api.sh regen     # both (default)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEMA_PATH="$SCRIPT_DIR/../src/api/schema.json"
OUTPUT_PATH="$SCRIPT_DIR/../src/api/generated/api.ts"
BASE_URL="${API_URL:-http://localhost:8000}"

fetch() {
  if [[ -n "${API_SPEC_PATH:-}" ]]; then
    echo "Copying canonical schema from $API_SPEC_PATH"
    cp "$API_SPEC_PATH" "$SCHEMA_PATH"
  else
    url="$BASE_URL/api/v1/openapi.json"
    echo "Fetching canonical schema from $url"
    curl -fsSL "$url" -o "$SCHEMA_PATH"
  fi
}

generate() {
  mkdir -p "$(dirname "$OUTPUT_PATH")"
  echo "Generating types from $SCHEMA_PATH"
  npx openapi-typescript "$SCHEMA_PATH" -o "$OUTPUT_PATH"
}

case "${1:-regen}" in
  fetch) fetch ;;
  generate) generate ;;
  regen) fetch; generate ;;
  *) echo "Unknown command: $1 (expected fetch|generate|regen)"; exit 2 ;;
esac

echo "Done."
