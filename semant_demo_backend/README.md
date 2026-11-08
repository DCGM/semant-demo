# SemANTDemoBackend

FastAPI backend of the SemANT demo. Structure and behavior:
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md). Shared development requirements:
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Installation and checks

Use Python 3.12. From the repository root:

```bash
make setup             # .venv with requirements-dev.lock, backend package, frontend npm ci
make check             # Ruff, fast pytest suite, frontend checks, API client drift
make test-integration  # real-Weaviate tests in a throwaway container (Docker)
```

Set `PYTHON=...` to select another interpreter. Without Make, the backend equivalents
(from the repository root) are:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r semant_demo_backend/requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e semant_demo_backend
(cd semant_demo_backend && ../.venv/bin/python -m ruff check .)
(cd semant_demo_backend && ../.venv/bin/python -m pytest -m "not integration and not live and not benchmark")
scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && ../.venv/bin/python -m pytest -m integration'
```

For the frontend portions of setup/check and API generation, see the
[frontend guide](../semant_demo_frontend/README.md#checks). Do not call backend-only
checks a complete `make check` pass. Ruff enforces syntax errors, undefined names and
unused imports (`pyproject.toml`); widen rules during cleanup rather than adding blanket
ignores.

### Dependency locks

The locks target CPython 3.12 on Linux x86_64:

- `requirements.txt` declares runtime dependencies; `requirements-dev.txt` adds test/lint
  tools. These are lock inputs, not files to install directly.
- `requirements-dev.lock` pins/hashes the full development set used by setup and CI.
- `requirements-runtime.lock` pins/hashes only runtime dependencies. It is compiled with
  the dev lock as a constraint, so `deploy/Dockerfile` installs the versions CI tests.

After changing either requirements input, install `pip-tools==7.6.2` in `.venv`, run
`make lock` (`scripts/python-locks.sh update`) from the repository root and review both
lock diffs. Existing pins are retained. Upgrade deliberately, for example
`LOCK_COMPILE_ARGS="--upgrade-package NAME" make lock`; `--upgrade` upgrades everything.
Preserve hashes: CI and the runtime image install with `--require-hashes`.

`tests/test_dependency_locks.py` checks input coverage and matching runtime pins. The CI
`python-locks` job installs the runtime lock separately (`pip check`, OpenAPI export) and
re-resolves both locks. Re-resolution takes minutes: on PRs it runs only when a path in
`LOCK_INPUTS` of `scripts/python-locks.sh` changed (requirements, locks, script/test or
workflows). Pushes to `main`, tags and manual runs always re-resolve;
`python-locks-drift.yml` does so weekly. Run `make lock-check` or the drift workflow on
demand. Deployments wait for this job; cache details are in [deploy/README.md](../deploy/README.md).

### Test locations and iteration

Use pytest and retain existing unittest tests. Unmarked tests are fast: `tests/conftest.py`
refuses network connections, including loopback. Use `tests/fakes.py` for AI providers and
construct apps with `create_app(Config(environ=...))`, not development stores.

From the repository root, select affected tests while iterating:

```bash
(cd semant_demo_backend && ../.venv/bin/python -m pytest tests/test_search_service.py -k access)
make test-integration ARGS="tests/integration/test_chunk_tags.py -k bulk"
```

`tests/integration` uses the `integration` marker and disposable Weaviate with synthetic
`tests/fixtures/corpus.json`, shared with browser tests. Tests clear/reseed their data and
recreate schema only when necessary. Store ownership and isolation:
[development guide](../docs/DEVELOPMENT.md#4-testing-versus-development-data).
`live` and `benchmark` tests are separately marked/opted into. Test selection and required
evidence are governed by [CONTRIBUTING](../CONTRIBUTING.md#4-testing-contract);
[ADR 0005](../docs/adr/0005-testing-contract.md) covers fixtures, async and regressions.

## Usage

Use the seeded local application, from the repository root:

```bash
make dev-up
make dev-backend    # terminal 1: backend and fake AI providers
make dev-frontend   # terminal 2
```

Lifecycle, accounts, safety and parallel-checkout support:
[docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md#1-quick-start-the-seeded-local-application).
Manual Uvicorn startup is an [authorized snapshot workflow](../docs/DEVELOPMENT.md#55-backend-and-frontend-by-hand),
not the default: it uses real provider configuration rather than the seeded fake profile.
