# SemANTDemoBackend

FastAPI backend of the SemANT demo. Structure and behavior: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

## Installation and checks

From the repository root (see [CONTRIBUTING.md](../CONTRIBUTING.md#2-setup-and-commands)):

```bash
make setup             # .venv with requirements-dev.lock, backend package, frontend npm ci
make check             # Ruff, fast pytest suite, frontend checks, API client drift
make test-integration  # real-Weaviate tests in a throwaway container (Docker)
```

## Usage

Use the local development databases described in [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md), then:

```bash
cd semant_demo_backend
../.venv/bin/python -m uvicorn semant_demo.main:app --reload
```
