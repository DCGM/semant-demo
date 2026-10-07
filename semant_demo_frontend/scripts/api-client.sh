#!/usr/bin/env bash
# Export the backend OpenAPI schema and generate the TypeScript client from it.
#
#   scripts/api-client.sh generate   replace src/generated/api with a fresh generation
#   scripts/api-client.sh check      fail if src/generated/api differs from a fresh generation
#
# The client is generated into an empty directory, so files the generator no longer
# produces are removed instead of lingering. Requires Java 11+ for the pinned generator
# (openapitools.json) and the backend Python environment ($PYTHON, default: python).
#
# CI overrides: OPENAPI_JSON uses an already exported schema instead of exporting one;
# OPENAPI_GENERATOR replaces the generator command (same pinned version, e.g. its jar).
set -euo pipefail

mode="${1:-}"
if [[ "$mode" != generate && "$mode" != check ]]; then
  echo "usage: $0 generate|check" >&2
  exit 2
fi

frontend="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend="$frontend/../semant_demo_backend"
client="$frontend/src/generated/api"
python="${PYTHON:-python}"
generator="${OPENAPI_GENERATOR:-npx --no-install openapi-generator-cli}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

if [[ -n "${OPENAPI_JSON:-}" ]]; then
  cp "$OPENAPI_JSON" "$work/openapi.json"
else
  (cd "$backend" && "$python" export_openapi.py --output "$work/openapi.json")
fi

mkdir "$work/api"
cp "$client/.openapi-generator-ignore" "$work/api/"
# shellcheck disable=SC2086 # $generator is a command with arguments
(cd "$frontend" && $generator generate \
  -i "$work/openapi.json" \
  -g typescript-fetch \
  -o "$work/api" \
  --additional-properties=supportsES6=true,typescriptThreePlus=true,modelPropertyNaming=camelCase,enumPropertyNaming=camelCase,withoutPrefixEnums=true,withInterfaces=true,useSingleRequestParameter=true \
  > "$work/generator.log") || { cat "$work/generator.log" >&2; exit 1; }

if [[ "$mode" == generate ]]; then
  rm -rf "$client"
  cp -R "$work/api" "$client"
  cp "$work/openapi.json" "$backend/openapi.json"
  echo "Generated client in src/generated/api (schema copied to semant_demo_backend/openapi.json)."
elif diff -r "$work/api" "$client" > "$work/drift.diff"; then
  echo "Generated API client is up to date."
else
  cat "$work/drift.diff"
  echo >&2
  echo "Generated API client differs from the backend schema. Run 'make api-generate' (or" >&2
  echo "'npm run api-generate' in semant_demo_frontend with PYTHON set) and commit the result." >&2
  exit 1
fi
