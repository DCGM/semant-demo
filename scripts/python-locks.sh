#!/usr/bin/env bash
# Generate or check the backend Python locks (#139).
#
#   scripts/python-locks.sh update   regenerate both locks in semant_demo_backend/
#   scripts/python-locks.sh check    re-resolve copies and fail if any pinned version differs
#   scripts/python-locks.sh check-since BASE
#                                    `check`, unless no lock input changed since git revision BASE
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
# `check-since` lets CI skip the slow re-resolution on PRs that leave every LOCK_INPUTS path
# unchanged (#367). It re-resolves whenever the diff cannot be computed. Unchanged inputs can
# still drift as the index changes; full `check` runs on main, tags, manual runs and weekly.
#
# LOCK_COMPILER selects the pip-compile executable (default: pip-compile on PATH). The
# variables are not named PIP_*: pip reads those as its own options.
set -euo pipefail

LOCK_COMPILER=${LOCK_COMPILER:-pip-compile}
# A relative path keeps working after `cd`.
[[ $LOCK_COMPILER == */* ]] && LOCK_COMPILER=$(realpath "$LOCK_COMPILER")
read -r -a EXTRA_ARGS <<< "${LOCK_COMPILE_ARGS:-}"
BACKEND=$(cd "$(dirname "$0")/../semant_demo_backend" && pwd)
ROOT=$(dirname "$BACKEND")

# Repository paths that can change the resolution or how it is verified.
LOCK_INPUTS=(
  semant_demo_backend/requirements.txt
  semant_demo_backend/requirements-dev.txt
  semant_demo_backend/requirements-dev.lock
  semant_demo_backend/requirements-runtime.lock
  semant_demo_backend/pyproject.toml
  semant_demo_backend/tests/test_dependency_locks.py
  scripts/python-locks.sh
  .github/workflows/
)

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
  check-since)
    base=${2:?usage: $0 check-since BASE}
    if changed=$(git -C "$ROOT" diff --name-only "$base" HEAD -- "${LOCK_INPUTS[@]}"); then
      if [[ -z $changed ]]; then
        echo "No lock input changed since $base; skipping re-resolution."
        exit 0
      fi
      echo "Lock inputs changed since $base:" $changed
    else
      echo "::warning::cannot diff against $base; re-resolving the locks" >&2
    fi
    exec "$0" check
    ;;
  *)
    echo "usage: $0 update|check|check-since BASE" >&2
    exit 2
    ;;
esac
