"""Deterministic application profile for browser tests (``make test-e2e``).

    python -m tests.e2e_server --port 8765 --static ../semant_demo_frontend/dist/e2e

Runs from ``semant_demo_backend``, after ``scripts/with-test-weaviate.sh`` has provided a
test-owned Weaviate. It

* resets the test store and seeds the fixture corpus (ownership verified first);
* creates a temporary SQLite database with the corpus users;
* serves the built frontend from the same origin as the API, and the same build again on
  ``port + 2``, the origin allowed for credentialed cross-origin requests: a browser test
  checks the guest cookie there across origins (local development: frontend :9000, API
  :8000);
* logs only warnings and errors (``E2E_LOG_LEVEL``, default ``WARNING``), so a failure is
  not buried under one ``HTTP request completed`` line per request; its own startup line
  is always shown;
* runs fake embedding/Topicer/LLM providers on ``port + 1`` and points every AI
  provider setting at them, with no API keys, so no live or paid provider can be reached
  (tiers on keyed providers are refused before any request).
  The Topicer stream pauses ``FAKE_TOPICER_STREAM_DELAY`` seconds between chunks, so
  browser tests can cancel or navigate while a suggestion run is under way.

Nothing here is used by the production application.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import signal
import sys
import tempfile
from pathlib import Path

import uvicorn
from starlette.staticfiles import StaticFiles

# Only modules that do not import `semant_demo.config`; see `serve`.
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app, fake_provider_environ
from tests.weaviate_store import StoreEndpoint

logger = logging.getLogger("e2e_server")

E2E_JWT_SECRET = "e2e-only-secret-long-enough-for-hmac-sha256-32bytes"
FAKE_TOPICER_STREAM_DELAY = 3.0


def profile_environ(endpoint: StoreEndpoint, work_dir: Path, static_dir: Path, fake_url: str, fake_port: int,
                    cross_origin: str) -> dict[str, str]:
    rag_dir = work_dir / "rag_configs"
    rag_dir.mkdir()
    return {
        **endpoint.app_environ(),
        **fake_provider_environ(work_dir, fake_url, fake_port),
        "SQL_DB_URL": f"sqlite+aiosqlite:///{work_dir / 'e2e.db'}",
        "JWT_SECRET": E2E_JWT_SECRET,
        "STATIC_PATH": str(static_dir),
        "ALLOWED_ORIGIN": cross_origin,
        "RAG_CONFIGS_PATH": str(rag_dir),
        "FEEDBACK_LOG_PATH": str(work_dir / "feedback.log.jsonl"),
        "FEEDBACK_WEBHOOK_URL": "",
        "PRODUCTION": "false",
    }


async def prepare_stores(config, endpoint: StoreEndpoint) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.seed import derive_annotations, seed_users, seed_weaviate
    from tests.weaviate_store import connect, create_app_schema, drop_app_collections

    corpus = load_corpus()
    client = await connect(endpoint)
    try:
        await drop_app_collections(client, config.collectionNames, endpoint.token)
        await create_app_schema(client, config.collectionNames)
        await seed_weaviate(client, config.collectionNames, corpus, endpoint.token)
        # Concordance rows (#329) read the derived text, as on a migrated store.
        await derive_annotations(client, config, corpus)
    finally:
        await client.close()
    engine = create_async_engine(config.SQL_DB_URL)
    try:
        await seed_users(engine, corpus)
    finally:
        await engine.dispose()


async def serve(port: int, static_dir: Path) -> None:
    endpoint = StoreEndpoint.from_env()
    fake_port = port + 1
    fake_url = f"http://127.0.0.1:{fake_port}"
    cross_port = port + 2
    work_dir = Path(tempfile.mkdtemp(prefix="semant-e2e-"))
    try:
        # Set before importing the application: importing `semant_demo.main` builds the
        # process-wide `config` (log level, the production `app`) from the environment.
        assert "semant_demo.config" not in sys.modules, "process-wide config created too early"
        os.environ.update(profile_environ(endpoint, work_dir, static_dir, fake_url, fake_port,
                                          cross_origin=f"http://127.0.0.1:{cross_port}"))
        from semant_demo.config import Config, config as process_config
        from semant_demo.main import create_app

        assert process_config.TOPICER_URL == fake_url

        config = Config()
        await prepare_stores(config, endpoint)
        servers = [
            uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1", port=port, log_level="warning")),
            uvicorn.Server(uvicorn.Config(create_fake_provider_app(load_corpus(), FAKE_TOPICER_STREAM_DELAY),
                                          host="127.0.0.1", port=fake_port, log_level="warning")),
            # The build alone, for its API requests to cross origins.
            uvicorn.Server(uvicorn.Config(StaticFiles(directory=static_dir, html=True),
                                          host="127.0.0.1", port=cross_port, log_level="warning")),
        ]
        logger.info("E2E app on http://127.0.0.1:%d, fake providers on %s, the frontend also on :%d",
                    port, fake_url, cross_port)
        # Each uvicorn server handles SIGINT/SIGTERM, then restores the previous handler and
        # re-raises the signal. A no-op base handler lets that end here, so all servers
        # stop and the temporary directory is removed below.
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: None)
        await asyncio.gather(*(s.serve() for s in servers))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--static", type=Path, required=True, help="built frontend (quasar build)")
    args = parser.parse_args()
    if not (args.static / "index.html").is_file():
        parser.error(f"{args.static} does not contain a built frontend (index.html)")
    logging.basicConfig(level=os.environ.get("E2E_LOG_LEVEL", "WARNING").upper())
    logger.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(serve(args.port, args.static.resolve()))


if __name__ == "__main__":
    main()
