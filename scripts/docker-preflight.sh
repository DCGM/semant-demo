#!/usr/bin/env bash
# Docker preflight shared by the Weaviate launchers (#674): local-dev.sh, with-test-weaviate.sh
# and, through it, e2e-dev.sh. It tells apart a missing Docker CLI, a daemon that is not
# running or not accessible, a daemon that does not answer in time, and an image that is
# neither present nor pullable, and prints the next step for each. It changes nothing except
# pulling the Weaviate image when it is missing.
#
#   scripts/docker-preflight.sh           check the Docker CLI and daemon (make docker-check)
#   scripts/docker-preflight.sh --image   also check that the Weaviate image is present,
#                                         pulling it if needed
#
# Sourced, it defines WEAVIATE_VERSION, weaviate_image, docker_ready and
# weaviate_image_ready; each prints its diagnosis to stderr and returns non-zero.
#
# SEMANT_DOCKER_TIMEOUT    seconds a daemon probe may take (default 10)
# SEMANT_DOCKER_PULL_TIMEOUT seconds an image pull may take (default 600)
# SEMANT_WEAVIATE_IMAGE    an explicitly chosen image to use instead of the canonical one,
#                          e.g. a mirror; its tag must be WEAVIATE_VERSION (see
#                          docs/DEVELOPMENT.md, "Docker and the Weaviate image")

# Same version as deployment (weaviate_utils/docker-compose.yml, docs/DEPLOYMENT.md).
WEAVIATE_VERSION="1.40.1"
WEAVIATE_CANONICAL_IMAGE="cr.weaviate.io/semitechnologies/weaviate:$WEAVIATE_VERSION"

_dp_say() { echo "docker-preflight: $*" >&2; }

# Run "$@" for at most $1 seconds (exit 124 on time-out). Without coreutils `timeout` the
# command runs unbounded.
_dp_bounded() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout -k 5 "$seconds" "$@"
  else
    "$@"
  fi
}

_dp_no_docker_hint() {
  _dp_say "  Without Docker you can still run: make deps-check, make check (lint, types, fast tests,"
  _dp_say "  API-client drift). make test-integration, make test-e2e, make e2e-dev-* and make dev-up"
  _dp_say "  need Docker (docs/DEVELOPMENT.md, \"Which checks need Docker\")."
}

# The image to use: the canonical one, or an explicit override (SEMANT_WEAVIATE_IMAGE, or the
# older SEMANT_TEST_WEAVIATE_IMAGE when $1 is "test"). An override must carry the required
# version tag, so a different Weaviate is never picked up by accident.
weaviate_image() {
  local image="${SEMANT_WEAVIATE_IMAGE:-}" source=SEMANT_WEAVIATE_IMAGE
  if [[ "${1:-}" == test && -n "${SEMANT_TEST_WEAVIATE_IMAGE:-}" ]]; then
    image="$SEMANT_TEST_WEAVIATE_IMAGE"
    source=SEMANT_TEST_WEAVIATE_IMAGE
  fi
  if [[ -z "$image" ]]; then
    echo "$WEAVIATE_CANONICAL_IMAGE"
    return 0
  fi
  # name[:tag][@digest]; the tag is after the last colon that follows the last slash.
  local name="${image%%@*}" tag=""
  [[ "${name##*/}" == *:* ]] && tag="${name##*:}"
  if [[ "$tag" != "$WEAVIATE_VERSION" ]]; then
    _dp_say "$source=$image is not tagged :$WEAVIATE_VERSION; only Weaviate $WEAVIATE_VERSION is supported"
    _dp_say "  (the version of deployment and of every test store). Use a $WEAVIATE_VERSION image, or unset $source."
    return 1
  fi
  _dp_say "using $image from $source instead of $WEAVIATE_CANONICAL_IMAGE"
  echo "$image"
}

docker_ready() {
  local seconds="${SEMANT_DOCKER_TIMEOUT:-10}" out rc=0
  if ! command -v docker >/dev/null 2>&1; then
    _dp_say "the docker command is not installed (not on PATH)."
    _dp_say "  Install Docker Engine or Docker Desktop (with WSL integration for this distribution on WSL)."
    _dp_no_docker_hint
    return 1
  fi
  out="$(_dp_bounded "$seconds" docker version --format '{{.Server.Version}}' 2>&1)" || rc=$?
  if [[ $rc -eq 0 ]]; then
    return 0
  fi
  if [[ $rc -eq 124 || $rc -eq 137 ]]; then
    _dp_say "the Docker daemon did not answer within ${seconds} s (docker version timed out)."
    _dp_say "  Docker Desktop may be starting or hung: wait and retry, or restart it (Linux: sudo systemctl"
    _dp_say "  restart docker). SEMANT_DOCKER_TIMEOUT=<seconds> allows a slower daemon."
    return 1
  fi
  _dp_say "the Docker daemon is not available. docker said:"
  sed '/^[[:space:]]*$/d; s/^/docker-preflight:   /' <<<"$out" >&2
  case "$out" in
    *"permission denied"*)
      _dp_say "  Your user may not access the daemon socket: add it to the docker group (then log in again),"
      _dp_say "  or use a rootless Docker." ;;
    *"could not be found in this WSL"*)
      _dp_say "  Start Docker Desktop and enable its WSL integration for this distribution." ;;
    *)
      _dp_say "  Start the daemon (Docker Desktop, or Linux: sudo systemctl start docker) and retry;"
      _dp_say "  check DOCKER_HOST / docker context if it is running elsewhere." ;;
  esac
  _dp_no_docker_hint
  return 1
}

# The image is present locally, or is pulled now. Call after docker_ready: a failure here is
# about the image or its registry, not the daemon.
weaviate_image_ready() {
  local image="$1" seconds="${SEMANT_DOCKER_TIMEOUT:-10}" pull_seconds="${SEMANT_DOCKER_PULL_TIMEOUT:-600}" rc=0
  _dp_bounded "$seconds" docker image inspect "$image" >/dev/null 2>&1 || rc=$?
  [[ $rc -eq 0 ]] && return 0
  if [[ $rc -eq 124 || $rc -eq 137 ]]; then
    _dp_say "the Docker daemon did not answer within ${seconds} s (docker image inspect timed out); retry, or restart Docker."
    return 1
  fi
  _dp_say "pulling $image (not present locally)"
  rc=0
  _dp_bounded "$pull_seconds" docker pull "$image" >&2 || rc=$?
  [[ $rc -eq 0 ]] && return 0
  if [[ $rc -eq 124 || $rc -eq 137 ]]; then
    _dp_say "pulling $image did not finish within ${pull_seconds} s; the registry is slow or unreachable."
  else
    _dp_say "could not pull $image (see the error above). The Docker daemon works; the registry or image is the problem."
  fi
  _dp_say "  Workarounds (Weaviate $WEAVIATE_VERSION only; docs/DEVELOPMENT.md, \"Docker and the Weaviate image\"):"
  _dp_say "  - retag a copy you obtained elsewhere: docker load -i weaviate-$WEAVIATE_VERSION.tar, or"
  _dp_say "    docker pull <mirror>/semitechnologies/weaviate:$WEAVIATE_VERSION, then"
  _dp_say "    docker tag <that image> $image"
  _dp_say "  - or select a mirror explicitly: SEMANT_WEAVIATE_IMAGE=<mirror>/semitechnologies/weaviate:$WEAVIATE_VERSION"
  [[ -n "${SEMANT_DOCKER_PULL_TIMEOUT:-}" ]] || _dp_say "  - a slow but working registry: SEMANT_DOCKER_PULL_TIMEOUT=<seconds>"
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  case "${1:-}" in
    "") docker_ready ;;
    --image) docker_ready; image="$(weaviate_image)"; weaviate_image_ready "$image" ;;
    *) sed -n '2,/^$/p' "$0" | sed -n 's/^# \{0,1\}//p' >&2; exit 2 ;;
  esac
  echo "docker-preflight: Docker works${image:+; $image is available}" >&2
fi
