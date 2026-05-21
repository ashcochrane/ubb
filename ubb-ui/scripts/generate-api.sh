#!/bin/bash
# Generates TypeScript types from django-ninja OpenAPI schemas.
#
# Two phases:
#   fetch    — pulls openapi.json from each namespace into src/api/schemas/
#              and strips the /api/v1/{ns} prefix so path keys line up with
#              how the openapi-fetch client calls them (the prefix is baked
#              into baseUrl in src/api/client.ts).
#   generate — runs openapi-typescript against the local snapshots into
#              src/api/generated/
#
# Commit both directories. Snapshots make the contract reviewable in PRs and
# let types be regenerated offline. CI can run `regen` + `git diff --exit-code`
# to catch drift.
#
# Usage:
#   ./generate-api.sh fetch     # snapshots only (requires Django dev server)
#   ./generate-api.sh generate  # types only (works offline)
#   ./generate-api.sh regen     # both (default)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEMA_DIR="$SCRIPT_DIR/../src/api/schemas"
OUT_DIR="$SCRIPT_DIR/../src/api/generated"
BASE_URL="${API_URL:-http://localhost:8000}"
APIS=("platform" "metering" "billing" "tenant" "me")

strip_prefix() {
  # Rewrites the openapi.json in-place, removing the /api/v1/{ns} prefix from
  # every path key. Django-ninja emits absolute mount paths but our client
  # already carries that prefix in baseUrl, so the types must reflect the
  # relative form the UI actually calls.
  local file="$1" ns="$2"
  python3 - "$file" "/api/v1/${ns}" <<'PY'
import json, sys
path, prefix = sys.argv[1], sys.argv[2]
with open(path) as f:
    spec = json.load(f)
paths = spec.get("paths", {})
rewritten = {}
for key, value in paths.items():
    if key.startswith(prefix):
        new_key = key[len(prefix):] or "/"
    else:
        new_key = key
    rewritten[new_key] = value
spec["paths"] = rewritten
with open(path, "w") as f:
    json.dump(spec, f, indent=2, sort_keys=True)
    f.write("\n")
PY
}

fetch() {
  mkdir -p "$SCHEMA_DIR"
  for api in "${APIS[@]}"; do
    url="$BASE_URL/api/v1/$api/openapi.json"
    echo "Fetching $api from $url"
    curl -fsSL "$url" -o "$SCHEMA_DIR/${api}.json"
    strip_prefix "$SCHEMA_DIR/${api}.json" "$api"
  done
}

generate() {
  mkdir -p "$OUT_DIR"
  for api in "${APIS[@]}"; do
    echo "Generating types for $api"
    npx openapi-typescript "$SCHEMA_DIR/${api}.json" -o "$OUT_DIR/${api}.ts"
  done
}

case "${1:-regen}" in
  fetch) fetch ;;
  generate) generate ;;
  regen) fetch; generate ;;
  *) echo "Unknown command: $1 (expected fetch|generate|regen)"; exit 2 ;;
esac

echo "Done."
