# Thin wrappers around the project's tool commands. Each recipe is the documented command;
# see CONTRIBUTING.md for running them without Make.

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
# Absolute path when PYTHON is a path, so recipes can change directory.
PY := $(if $(findstring /,$(PYTHON)),$(abspath $(PYTHON)),$(PYTHON))
FAST_TESTS := not integration and not live and not benchmark

.PHONY: setup check check-backend check-frontend api-generate api-check lock lock-check test-integration test-e2e

## Install pinned development dependencies (backend venv and frontend node_modules).
setup:
	test -x $(PYTHON) || python3.12 -m venv $(VENV)
	$(PY) -m pip install -r semant_demo_backend/requirements-dev.lock
	$(PY) -m pip install --no-deps -e semant_demo_backend
	cd semant_demo_frontend && npm ci

## Fast offline checks: lint, types, unit tests and generated-client drift.
check: check-backend check-frontend api-check

check-backend:
	cd semant_demo_backend && $(PY) -m ruff check .
	cd semant_demo_backend && $(PY) -m pytest -m "$(FAST_TESTS)"

check-frontend:
	cd semant_demo_frontend && npm run lint
	cd semant_demo_frontend && npm run typecheck
	cd semant_demo_frontend && npm test

## Real-Weaviate tests in a throwaway, test-owned Weaviate container (needs Docker).
test-integration:
	scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && "$(PY)" -m pytest -m integration'

## Browser smoke tests: build the frontend and run it against the deterministic backend
## profile (test-owned Weaviate, fixture corpus, fake AI providers). Needs Docker.
test-e2e:
	cd semant_demo_frontend && npx playwright install --only-shell chromium
	scripts/with-test-weaviate.sh sh -c 'cd semant_demo_frontend && PYTHON="$(PY)" npm run test:e2e'

## Regenerate the TypeScript client from the backend schema (needs Java 11+).
api-generate:
	cd semant_demo_frontend && PYTHON=$(PY) npm run api-generate

api-check:
	cd semant_demo_frontend && PYTHON=$(PY) npm run api-check

## Regenerate the backend Python locks after changing requirements*.txt (needs pip-tools).
lock:
	LOCK_COMPILER=$(VENV)/bin/pip-compile scripts/python-locks.sh update

## Fail if either backend Python lock is stale for its requirements (needs network).
lock-check:
	LOCK_COMPILER=$(VENV)/bin/pip-compile scripts/python-locks.sh check
