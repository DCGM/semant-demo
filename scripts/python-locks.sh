#!/usr/bin/env bash
# Generate or check the backend Python locks (#139).
#
#   scripts/python-locks.sh update   regenerate both locks in semant_demo_backend/
#   scripts/python-locks.sh check    re-resolve copies and fail if any pinned version differs
#
# requirements-dev.lock (runtime + test tools, installed by CI and `make setup`) is compiled
# first; requirements-runtime.lock (installed by deploy/Dockerfile) is then compiled from
# requirements.txt with the dev lock as a constraint, so production gets the tested versions.
# Existing pins are kept unless an input changed; `update` with LOCK_COMPILE_ARGS=--upgrade or
# "--upgrade-package NAME" upgrades deliberately. Target: CPython 3.12 on Linux x86_64.
#
# `check` compares names and versions only. Hashes are not compared because PyPI may add
# wheels to an already pinned release; every install verifies hashes with --require-hashes.
#
# LOCK_COMPILER selects the pip-compile executable (default: pip-compile on PATH). The
# variables are not named PIP_*: pip reads those as its own options.
set -euo pipefail

LOCK_COMPILER=${LOCK_COMPILER:-pip-compile}
# A relative path keeps working after `cd`.
[[ $LOCK_COMPILER == */* ]] && LOCK_COMPILER=$(realpath "$LOCK_COMPILER")
read -r -a EXTRA_ARGS <<< "${LOCK_COMPILE_ARGS:-}"
BACKEND=$(cd "$(dirname "$0")/../semant_demo_backend" && pwd)

compile() {
  "$LOCK_COMPILER" --quiet --allow-unsafe --generate-hashes --no-emit-index-url --strip-extras \
    "${EXTRA_ARGS[@]}" "$@"
}

update() {
  cd "$1"
  compile --output-file=requirements-dev.lock requirements-dev.txt
  compile --constraint=requirements-dev.lock --output-file=requirements-runtime.lock requirements.txt
}

pins() {
  sed -n 's/^\([A-Za-z0-9._-]*==[^ ;\\]*\).*/\1/p' "$1"
}

case "${1:-}" in
  update)
    update "$BACKEND"
    ;;
  check)
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT
    cp "$BACKEND"/requirements.txt "$BACKEND"/requirements-dev.txt \
      "$BACKEND"/requirements-dev.lock "$BACKEND"/requirements-runtime.lock "$work"/
    (update "$work")
    status=0
    for lock in requirements-dev.lock requirements-runtime.lock; do
      if ! diff -u --label "committed $lock" --label "re-resolved $lock" \
          <(pins "$BACKEND/$lock") <(pins "$work/$lock"); then
        echo "::error::$lock is stale; run scripts/python-locks.sh update and review the diff" >&2
        status=1
      fi
    done
    exit "$status"
    ;;
  *)
    echo "usage: $0 update|check" >&2
    exit 2
    ;;
esac
