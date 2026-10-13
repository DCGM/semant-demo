#!/usr/bin/env bash
# Fast local loop for browser tests: start the deterministic E2E profile once, then run
# selected Playwright specs against it repeatedly. Opt-in developer tooling; `make test-e2e`
# (hermetic full suite) and CI do not use it.
#
#   scripts/e2e-dev.sh start              build the frontend (unless the build is current), start
#                                         a throwaway Weaviate and the seeded e2e_server in the
#                                         background
#   scripts/e2e-dev.sh test <args...>     run Playwright against it; select a spec path and/or
#                                         --grep, e.g.
#                                         test test/e2e/searchResultCards.spec.ts --grep phone
#   scripts/e2e-dev.sh test --all [...]   run the whole suite against it
#   scripts/e2e-dev.sh capture [args...]  screenshots at wide desktop, narrow desktop with both
#                                         sidebars and phone (test/capture + selected specs)
#   scripts/e2e-dev.sh rebuild            rebuild the frontend into the served directory
#   scripts/e2e-dev.sh restart            stop, then start again (fresh Weaviate and seed)
#   scripts/e2e-dev.sh status | stop | logs
#
# The Weaviate container comes from scripts/with-test-weaviate.sh (own name, no volume, fresh
# ownership token) and is removed on `stop`; it never touches local_data/ or the development
# container, and `start` refuses an inherited SEMANT_TEST_WEAVIATE_HOST (an external store).
# The profile listens on E2E_DEV_PORT (default 8775, fake providers on the next port), so it
# does not collide with `make test-e2e` on 8765. A running profile keeps its port; a
# different E2E_DEV_PORT is refused until `stop`.
#
# `test` refuses to run when the frontend sources changed since the served build (run
# `rebuild`) or the backend sources/fixtures changed since start (run `restart`): a stale
# server is never mistaken for the code under test. Test spec files are not part of either
# fingerprint, so editing a spec needs no rebuild.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$ROOT/semant_demo_frontend"
BACKEND="$ROOT/semant_demo_backend"
STATE="${E2E_DEV_STATE:-$ROOT/.e2e-dev}"
PORT="${E2E_DEV_PORT:-8775}"
DIST="dist/e2e-dev"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PYTHON" in /*) ;; */*) PYTHON="$(cd "$(dirname "$PYTHON")" && pwd)/$(basename "$PYTHON")" ;; esac

# What the served build / the running backend were made from (tracked and untracked,
# non-ignored files). Spec files and the Playwright config are excluded on purpose.
FRONTEND_PATHS=(semant_demo_frontend ':(exclude)semant_demo_frontend/test' ':(exclude)semant_demo_frontend/playwright.config.ts')
BACKEND_PATHS=(semant_demo_backend/semant_demo semant_demo_backend/tests semant_demo_backend/requirements.txt
  ':(exclude,glob)semant_demo_backend/tests/**/test_*.py' ':(exclude)semant_demo_backend/tests/conftest.py')

die() { echo "e2e-dev: $*" >&2; exit 1; }

fingerprint() {
  (cd "$ROOT" && git ls-files -co --exclude-standard -z -- "$@" | sort -z \
    | xargs -0 sha256sum 2>&1 | sha256sum | cut -c1-16)
}

# BACKEND_URL is compiled into the build, so the port is part of what a build was made for.
frontend_stamp() { echo "port=$PORT $(fingerprint "${FRONTEND_PATHS[@]}")"; }

server_pid() { cat "$STATE/server.pid" 2>/dev/null || true; }
server_alive() { local pid; pid="$(server_pid)"; [[ -n "$pid" ]] && kill -0 -- "-$pid" 2>/dev/null; }
healthy() { curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; }
# The container name with-test-weaviate.sh printed for this server.
container_name() {
  [[ -f "$STATE/server.log" ]] || return 0
  sed -n 's/^Test Weaviate \(semant-weaviate-test-[0-9-]*\):.*/\1/p' "$STATE/server.log" | head -n1
}

build() {
  echo "e2e-dev: building the frontend into semant_demo_frontend/$DIST (BACKEND_URL :$PORT)" >&2
  local stamp
  stamp="$(frontend_stamp)"
  (cd "$FRONTEND" && QUASAR_DIST_DIR="$DIST" BACKEND_URL="http://127.0.0.1:${PORT}" npx quasar build >"$STATE/build.log" 2>&1) \
    || { tail -n 40 "$STATE/build.log" >&2; die "frontend build failed (full log: .e2e-dev/build.log)"; }
  # The fingerprint from before the build: an edit during the build counts as stale.
  echo "$stamp" >"$STATE/frontend.stamp"
}

# A running profile was built and started for its own port; adopt it, and refuse another.
use_session_port() {
  local session
  server_alive || return 0
  session="$(cat "$STATE/server.port" 2>/dev/null || true)"
  [[ -n "$session" ]] || return 0
  if [[ -n "${E2E_DEV_PORT:-}" && "$E2E_DEV_PORT" != "$session" ]]; then
    die "the running profile uses port $session, not E2E_DEV_PORT=$E2E_DEV_PORT; stop it first"
  fi
  PORT="$session"
}

# with-test-weaviate.sh would use that store instead of starting a disposable one.
refuse_external_store() {
  if [[ -n "${SEMANT_TEST_WEAVIATE_HOST:-}" ]]; then
    die "SEMANT_TEST_WEAVIATE_HOST is set; the fast loop always starts its own throwaway Weaviate, unset it"
  fi
}

cmd_start() {
  refuse_external_store
  mkdir -p "$STATE"
  if server_alive; then
    die "already running (pid $(server_pid), http://127.0.0.1:$PORT); use restart or stop"
  fi
  if healthy; then
    die "something else answers on http://127.0.0.1:$PORT; stop it or set E2E_DEV_PORT"
  fi
  [[ -x "$PYTHON" ]] || die "no Python at $PYTHON (make setup, or set PYTHON)"
  command -v docker >/dev/null || die "docker is required"
  rm -f "$STATE/server.pid" "$STATE/server.port" "$STATE/backend.stamp"

  local started=$SECONDS
  if [[ -f "$FRONTEND/$DIST/index.html" \
        && "$(cat "$STATE/frontend.stamp" 2>/dev/null)" == "$(frontend_stamp)" ]]; then
    echo "e2e-dev: frontend build is current, not rebuilding" >&2
  else
    build
  fi

  local backend_stamp
  backend_stamp="$(fingerprint "${BACKEND_PATHS[@]}")"
  # Own session and process group, so `stop` can signal the wrapper and the server together.
  # with-test-weaviate.sh removes its container when the server exits.
  setsid "$ROOT/scripts/with-test-weaviate.sh" sh -c \
    'cd "$1" && exec "$2" -m tests.e2e_server --port "$3" --static "$4"' \
    e2e-dev "$BACKEND" "$PYTHON" "$PORT" "$FRONTEND/$DIST" \
    >"$STATE/server.log" 2>&1 </dev/null &
  echo $! >"$STATE/server.pid"
  echo "$PORT" >"$STATE/server.port"

  for _ in $(seq 1 480); do
    healthy && break
    server_alive || { tail -n 40 "$STATE/server.log" >&2; cmd_stop >/dev/null; die "the profile exited during startup"; }
    sleep 0.5
  done
  if ! healthy; then
    tail -n 40 "$STATE/server.log" >&2
    cmd_stop >/dev/null
    die "the profile did not become healthy"
  fi
  echo "$backend_stamp" >"$STATE/backend.stamp"
  echo "e2e-dev: ready in $((SECONDS - started)) s on http://127.0.0.1:$PORT (Weaviate $(container_name)); log in e.g. as owner / owner-password-1" >&2
}

cmd_stop() {
  local pid name
  pid="$(server_pid)"
  name="$(container_name)"
  # The wrapper leads its own process group (setsid). Signal the group, which also reaches
  # a server left behind by a killed wrapper: SIGTERM lets the server remove its temporary
  # directory and the wrapper remove its container.
  if [[ -n "$pid" ]] && kill -0 -- "-$pid" 2>/dev/null; then
    kill -TERM -- "-$pid" 2>/dev/null || true
    for _ in $(seq 1 60); do kill -0 -- "-$pid" 2>/dev/null || break; sleep 0.5; done
    kill -KILL -- "-$pid" 2>/dev/null || true
  fi
  # Only the container this server started (e.g. if the wrapper itself was killed).
  if [[ -n "$name" ]] && docker inspect "$name" >/dev/null 2>&1; then
    docker rm -f "$name" >/dev/null
  fi
  rm -f "$STATE/server.pid" "$STATE/server.port" "$STATE/backend.stamp"
  echo "e2e-dev: stopped" >&2
}

check_current() {
  server_alive || die "not running; start it with: scripts/e2e-dev.sh start"
  healthy || die "running (pid $(server_pid)) but http://127.0.0.1:$PORT/health does not answer; see scripts/e2e-dev.sh logs, or restart"
  [[ "$(cat "$STATE/frontend.stamp" 2>/dev/null)" == "$(frontend_stamp)" ]] \
    || die "the served build is not from the current frontend sources for port $PORT; run: scripts/e2e-dev.sh rebuild"
  [[ "$(cat "$STATE/backend.stamp" 2>/dev/null)" == "$(fingerprint "${BACKEND_PATHS[@]}")" ]] \
    || die "backend sources or fixtures changed since start; run: scripts/e2e-dev.sh restart"
}

# Positional arguments that name a spec file must exist; Playwright would treat a typo as a
# filter. A filter that matches nothing fails ("No tests found"), it never widens the run.
check_args() {
  local arg
  for arg in "$@"; do
    if [[ "$arg" != -* && "$arg" == *.spec.ts ]]; then
      [[ -e "$FRONTEND/$arg" || -e "$ROOT/$arg" ]] || die "no such spec file: $arg"
    fi
  done
}

playwright() {
  check_args "$@"
  check_current
  cd "$FRONTEND"
  # Headless Chromium stalls ~25 s on its first frame when DISPLAY points at a forwarded
  # X server (ssh -X); it does not need a display unless a window is requested.
  if [[ " $* " != *" --headed "* && " $* " != *" --debug "* && " $* " != *" --ui "* ]]; then
    unset DISPLAY
  fi
  E2E_PORT="$PORT" E2E_EXTERNAL_SERVER=1 exec npx playwright test "$@"
}

# Only `--all` runs the whole suite: other options alone (--headed, --project=...) must
# select something, a spec/directory path or a --grep.
has_selection() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --grep|--grep=*|-g) return 0 ;;
      -*) ;;
      */*|*.ts) return 0 ;;
    esac
  done
  return 1
}

cmd_test() {
  if [[ "${1:-}" == "--all" ]]; then
    shift
  elif ! has_selection "$@"; then
    die "select a spec path or --grep (e.g. test test/e2e/smoke.spec.ts --grep login), or pass --all for the whole suite"
  fi
  playwright "$@"
}

cmd_capture() {
  export E2E_CAPTURE=1
  # Only the view captures unless a spec is named: options alone (--project=phone) must not
  # widen the run to every browser spec.
  local arg
  for arg in "$@"; do
    if [[ "$arg" != -* && ( "$arg" == *.spec.ts || "$arg" == test/* ) ]]; then
      playwright "$@"; return
    fi
  done
  playwright test/capture "$@"
}

cmd_rebuild() {
  mkdir -p "$STATE"
  build
  if server_alive; then
    echo "e2e-dev: the running server serves the new build (data and session state are kept)" >&2
  fi
}

cmd_status() {
  local name
  name="$(container_name)"
  if server_alive; then
    echo "running: pid $(server_pid), http://127.0.0.1:$PORT, Weaviate ${name:-?}, $(healthy && echo healthy || echo 'not answering')"
  else
    echo "not running"
  fi
  if [[ -f "$STATE/frontend.stamp" ]]; then
    [[ "$(cat "$STATE/frontend.stamp")" == "$(frontend_stamp)" ]] \
      && echo "frontend build: current for port $PORT" || echo "frontend build: stale for port $PORT (rebuild)"
  fi
  if [[ -f "$STATE/backend.stamp" ]]; then
    [[ "$(cat "$STATE/backend.stamp")" == "$(fingerprint "${BACKEND_PATHS[@]}")" ]] \
      && echo "backend: current" || echo "backend: stale (restart)"
  fi
}

command="${1:-}"
shift || true
case "$command" in
  start) use_session_port; cmd_start "$@" ;;
  stop) cmd_stop ;;
  restart) use_session_port; refuse_external_store; cmd_stop; cmd_start ;;
  rebuild) use_session_port; cmd_rebuild ;;
  test) use_session_port; cmd_test "$@" ;;
  capture) use_session_port; cmd_capture "$@" ;;
  status) use_session_port; cmd_status ;;
  logs) exec cat "$STATE/server.log" ;;
  *) sed -n '2,/^set /p' "$0" | sed -n 's/^# \{0,1\}//p' >&2; exit 2 ;;
esac
