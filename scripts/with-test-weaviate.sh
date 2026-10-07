#!/usr/bin/env bash
# Run a command against a throwaway Weaviate owned by this run.
#
#   scripts/with-test-weaviate.sh <command> [args...]
#
# Starts a uniquely named container with no volume (data lives only in the container)
# on random loopback ports, exports SEMANT_TEST_WEAVIATE_HOST/_REST_PORT/_GRPC_PORT and a
# fresh per-run ownership token SEMANT_TEST_STORE_TOKEN for the command, and removes the
# container afterwards, also on failure or Ctrl-C. It never touches the development
# container (semant-weaviate-dev) or local_data/.
#
# If SEMANT_TEST_WEAVIATE_HOST is already set (e.g. a CI service container), no container
# is started and the caller must also set SEMANT_TEST_STORE_TOKEN; the tests refuse an
# instance whose ownership marker does not hold that token.
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi

if [[ -n "${SEMANT_TEST_WEAVIATE_HOST:-}" ]]; then
  exec "$@"
fi

# Same version as the deployed and local development Weaviate (docs/DEVELOPMENT.md).
IMAGE="${SEMANT_TEST_WEAVIATE_IMAGE:-cr.weaviate.io/semitechnologies/weaviate:1.34.4}"
NAME="semant-weaviate-test-$(date +%s)-$$"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run -d --rm \
  --name "$NAME" \
  --label org.semant.purpose=automated-tests \
  -p 127.0.0.1::8080 \
  -p 127.0.0.1::50051 \
  -e QUERY_DEFAULTS_LIMIT=25 \
  -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
  -e PERSISTENCE_DATA_PATH=/var/lib/weaviate \
  -e DEFAULT_VECTORIZER_MODULE=none \
  -e CLUSTER_HOSTNAME=node1 \
  -e DISABLE_TELEMETRY=true \
  "$IMAGE" --host 0.0.0.0 --port 8080 --scheme http >/dev/null

port_of() { docker port "$NAME" "$1" | head -n1 | sed 's/.*://'; }
REST_PORT="$(port_of 8080/tcp)"
GRPC_PORT="$(port_of 50051/tcp)"

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:${REST_PORT}/v1/.well-known/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -fsS "http://127.0.0.1:${REST_PORT}/v1/.well-known/ready" >/dev/null 2>&1; then
  echo "Test Weaviate ($NAME) did not become ready." >&2
  docker logs "$NAME" >&2 || true
  exit 1
fi

echo "Test Weaviate $NAME: REST 127.0.0.1:${REST_PORT}, gRPC 127.0.0.1:${GRPC_PORT}" >&2
export SEMANT_TEST_WEAVIATE_HOST=127.0.0.1
export SEMANT_TEST_WEAVIATE_REST_PORT="$REST_PORT"
export SEMANT_TEST_WEAVIATE_GRPC_PORT="$GRPC_PORT"
# Unique per run: the tests only use a store whose marker holds this exact token.
SEMANT_TEST_STORE_TOKEN="${NAME}-$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
export SEMANT_TEST_STORE_TOKEN

# Not exec: the EXIT trap must remove the container after the command finishes.
"$@"
