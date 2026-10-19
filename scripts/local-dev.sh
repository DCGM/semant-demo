#!/usr/bin/env bash
# Persistent, seeded local development environment (#438; docs/DEVELOPMENT.md).
#
#   scripts/local-dev.sh up        start the development Weaviate; on first use seed it and
#                                  the SQLite database with the fixture corpus (never reseeds)
#   scripts/local-dev.sh backend   fake AI providers + Uvicorn --reload on :8000 (foreground)
#   scripts/local-dev.sh frontend  Quasar dev server with hot reload on :9000 (foreground)
#   scripts/local-dev.sh down      stop Weaviate; its data volume and SQLite are kept
#   scripts/local-dev.sh reset     show what would be destroyed; with CONFIRM=yes (or typed
#                                  confirmation) drop both stores and reseed the corpus
#   scripts/local-dev.sh status | verify | logs
#
# Weaviate runs in the container semant-weaviate-local on the labelled Docker volume
# semant-local-weaviate (REST 127.0.0.1:8180, gRPC 127.0.0.1:50151); SQLite is
# .dev-data/semant.db. Neither is local_data/ (snapshots) nor anything of the automated
# tests. Every command that writes checks that the container and volume carry the
# local-development label and that the container is the one on the configured port; the
# Python side (semant_demo_backend/tests/local_dev.py) then checks the ownership marker
# in both stores. One instance per machine: the container and volume names are fixed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/semant_demo_backend"
FRONTEND="$ROOT/semant_demo_frontend"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PYTHON" in /*) ;; */*) PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")" ;; esac

# Same version as deployment and the test stores (scripts/with-test-weaviate.sh).
IMAGE="cr.weaviate.io/semitechnologies/weaviate:1.40.1"
NAME="semant-weaviate-local"
VOLUME="semant-local-weaviate"
LABEL="org.semant.purpose=local-development"
export SEMANT_DEV_WEAVIATE_REST_PORT="${SEMANT_DEV_WEAVIATE_REST_PORT:-8180}"
export SEMANT_DEV_WEAVIATE_GRPC_PORT="${SEMANT_DEV_WEAVIATE_GRPC_PORT:-50151}"
export SEMANT_DEV_PROVIDER_PORT="${SEMANT_DEV_PROVIDER_PORT:-8009}"
BACKEND_PORT="${SEMANT_DEV_BACKEND_PORT:-8000}"
FRONTEND_PORT=9000
REST="$SEMANT_DEV_WEAVIATE_REST_PORT"

die() { echo "local-dev: $*" >&2; exit 1; }
say() { echo "local-dev: $*" >&2; }

need_python() { [[ -x "$PYTHON" ]] || die "no Python at $PYTHON (run make setup, or set PYTHON)"; }
need_docker() { command -v docker >/dev/null || die "docker is required for the development Weaviate"; }
local_dev() { (cd "$BACKEND" && "$PYTHON" -m tests.local_dev "$@"); }

listening() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
label_of() { docker "$1" inspect --format '{{ index .'"$2"' "org.semant.purpose" }}' "$3" 2>/dev/null || true; }
container_exists() { docker container inspect "$NAME" >/dev/null 2>&1; }
container_running() { [[ "$(docker container inspect --format '{{.State.Running}}' "$NAME" 2>/dev/null)" == true ]]; }
ready() { curl -fsS "http://127.0.0.1:$REST/v1/.well-known/ready" >/dev/null 2>&1; }

# The container and its volume are ours, and the container is what answers on $REST.
check_owned() {
  [[ "$(label_of volume Labels "$VOLUME")" == local-development ]] \
    || die "Docker volume $VOLUME is missing or has no $LABEL label; refusing to use it"
  container_running || die "the development Weaviate is not running; start it with: make dev-up"
  [[ "$(label_of container Config.Labels "$NAME")" == local-development ]] \
    || die "container $NAME has no $LABEL label; refusing to use it"
  local mount port
  mount="$(docker container inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/weaviate"}}{{.Name}}{{end}}{{end}}' "$NAME")"
  [[ "$mount" == "$VOLUME" ]] || die "container $NAME does not store its data on volume $VOLUME; refusing to use it"
  port="$(docker port "$NAME" 8080/tcp 2>/dev/null | head -n1)"
  [[ "$port" == "127.0.0.1:$REST" ]] \
    || die "container $NAME publishes REST on '${port:-nothing}', not 127.0.0.1:$REST; run make dev-down, then make dev-up"
}

start_weaviate() {
  need_docker
  if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    [[ "$(label_of volume Labels "$VOLUME")" == local-development ]] \
      || die "a Docker volume $VOLUME exists without the $LABEL label; not using it"
  else
    docker volume create --label "$LABEL" "$VOLUME" >/dev/null
    say "created Docker volume $VOLUME"
  fi
  if container_exists; then
    [[ "$(label_of container Config.Labels "$NAME")" == local-development ]] \
      || die "a container named $NAME exists without the $LABEL label; not touching it"
    container_running || docker start "$NAME" >/dev/null
  else
    if listening "$REST" || listening "$SEMANT_DEV_WEAVIATE_GRPC_PORT"; then
      die "port $REST or $SEMANT_DEV_WEAVIATE_GRPC_PORT is already in use; stop that service or set SEMANT_DEV_WEAVIATE_REST_PORT / SEMANT_DEV_WEAVIATE_GRPC_PORT"
    fi
    docker run -d --rm \
      --name "$NAME" \
      --label "$LABEL" \
      --stop-timeout 120 \
      -p "127.0.0.1:$REST:8080" \
      -p "127.0.0.1:$SEMANT_DEV_WEAVIATE_GRPC_PORT:50051" \
      --mount "type=volume,source=$VOLUME,target=/var/lib/weaviate" \
      -e QUERY_DEFAULTS_LIMIT=25 \
      -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true \
      -e PERSISTENCE_DATA_PATH=/var/lib/weaviate \
      -e DEFAULT_VECTORIZER_MODULE=none \
      -e CLUSTER_HOSTNAME=node1 \
      -e DISABLE_TELEMETRY=true \
      "$IMAGE" --host 0.0.0.0 --port 8080 --scheme http >/dev/null \
      || die "could not start $NAME (port conflict? see the Docker error above)"
    say "started $NAME (REST 127.0.0.1:$REST, gRPC 127.0.0.1:$SEMANT_DEV_WEAVIATE_GRPC_PORT)"
  fi
  for _ in $(seq 1 120); do ready && break; sleep 0.5; done
  ready || { docker logs --tail 40 "$NAME" >&2 || true; die "Weaviate did not become ready"; }
  check_owned
}

cmd_up() {
  need_python
  start_weaviate
  local_dev init || die "initialization failed or was refused; nothing else was changed (see above)"
  say "ready. Next, in two terminals: make dev-backend   and   make dev-frontend"
}

cmd_down() {
  need_docker
  if container_exists; then
    [[ "$(label_of container Config.Labels "$NAME")" == local-development ]] \
      || die "container $NAME has no $LABEL label; not touching it"
    docker stop "$NAME" >/dev/null
    say "stopped $NAME; data kept in volume $VOLUME and .dev-data/"
  else
    say "$NAME is not running; data kept in volume $VOLUME and .dev-data/"
  fi
}

cmd_backend() {
  need_python
  need_docker
  check_owned
  local_dev check || exit 1
  local port
  for port in "$BACKEND_PORT" "$SEMANT_DEV_PROVIDER_PORT"; do
    listening "$port" && die "port $port is already in use (another backend or provider process?)"
  done
  eval "$(local_dev environ)"
  (cd "$BACKEND" && exec "$PYTHON" -m tests.local_dev providers) &
  local providers=$!
  trap 'kill "$providers" 2>/dev/null || true; wait "$providers" 2>/dev/null || true' EXIT
  trap 'exit 130' INT TERM
  for _ in $(seq 1 40); do listening "$SEMANT_DEV_PROVIDER_PORT" && break; sleep 0.25; done
  listening "$SEMANT_DEV_PROVIDER_PORT" || die "the fake providers did not start"
  say "backend with --reload on http://127.0.0.1:$BACKEND_PORT (API docs /docs); AI providers are fakes"
  cd "$BACKEND"
  "$PYTHON" -m uvicorn semant_demo.main:app --reload --reload-dir semant_demo \
    --host 127.0.0.1 --port "$BACKEND_PORT"
}

cmd_frontend() {
  [[ -d "$FRONTEND/node_modules" ]] || die "frontend dependencies are missing; run make setup"
  listening "$FRONTEND_PORT" && die "port $FRONTEND_PORT is already in use; the backend only allows the origin http://localhost:$FRONTEND_PORT"
  say "open http://localhost:$FRONTEND_PORT (log in e.g. as owner / owner-password-1)"
  cd "$FRONTEND"
  BACKEND_URL="http://localhost:$BACKEND_PORT" exec npx quasar dev --port "$FRONTEND_PORT"
}

cmd_reset() {
  need_python
  # A running backend would keep using the deleted SQLite file and its cached state.
  listening "$BACKEND_PORT" && die "something listens on :$BACKEND_PORT; stop make dev-backend before a reset"
  start_weaviate
  local_dev reset || die "reset refused; nothing was changed (see above)"
  if [[ "${CONFIRM:-}" != yes ]]; then
    [[ -t 0 ]] || die "not confirmed; nothing was changed. Run: make dev-reset CONFIRM=yes"
    local answer
    read -r -p "Type 'reset' to destroy and reseed the development data: " answer
    [[ "$answer" == reset ]] || die "not confirmed; nothing was changed"
  fi
  local_dev reset --yes || die "reset failed; run make dev-reset again to start over"
}

cmd_status() {
  need_docker
  if ! container_running; then
    echo "Weaviate $NAME: not running (volume $VOLUME $(docker volume inspect "$VOLUME" >/dev/null 2>&1 && echo exists || echo 'does not exist'))"
    return 0
  fi
  check_owned
  need_python
  local_dev status
}

command="${1:-}"
shift || true
case "$command" in
  up) cmd_up ;;
  down) cmd_down ;;
  backend) cmd_backend ;;
  frontend) cmd_frontend ;;
  reset) cmd_reset ;;
  status) cmd_status ;;
  verify) need_python; need_docker; check_owned; local_dev verify ;;
  logs) exec docker logs "$NAME" ;;
  *) sed -n '2,/^set /p' "$0" | sed -n 's/^# \{0,1\}//p' >&2; exit 2 ;;
esac
