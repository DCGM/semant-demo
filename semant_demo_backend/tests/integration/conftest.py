"""Fixtures for tests against a real, test-owned Weaviate (``make test-integration``).

Tests in this package must carry ``pytestmark = pytest.mark.integration``. A missing or
unowned store is an error, not a skip, so a required integration run cannot pass
without exercising Weaviate.
"""
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from semant_demo.config import Config
from semant_demo.main import create_app
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
from tests.app_support import make_test_config
from tests.corpus import load_corpus
from tests.seed import seed_users, seed_weaviate
from tests.weaviate_store import StoreEndpoint, connect, create_app_schema, drop_app_collections


@pytest.fixture
def corpus():
    return load_corpus()


@pytest.fixture
def collection_names():
    return Config(environ={}).collectionNames


@pytest.fixture
def store_endpoint() -> StoreEndpoint:
    return StoreEndpoint.from_env()


@pytest.fixture
async def weaviate_client(store_endpoint):
    client = await connect(store_endpoint)
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
async def seeded_store(weaviate_client, collection_names, corpus):
    """Fresh application collections holding the fixture corpus; dropped afterwards."""
    # Also removes leftovers of an interrupted earlier test in this owned instance.
    await drop_app_collections(weaviate_client, collection_names)
    await create_app_schema(weaviate_client, collection_names)
    await seed_weaviate(weaviate_client, collection_names, corpus)
    try:
        yield weaviate_client
    finally:
        await drop_app_collections(weaviate_client, collection_names)


@pytest.fixture
def searcher(seeded_store, collection_names) -> WeaviateAbstraction:
    return WeaviateAbstraction(seeded_store, collection_names)


@pytest.fixture
async def api_client(tmp_path, store_endpoint, seeded_store, corpus):
    """HTTP client for an app using the seeded store and a SQLite database with corpus users."""
    config = make_test_config(tmp_path, **store_endpoint.app_environ())
    engine = create_async_engine(config.SQL_DB_URL)
    try:
        await seed_users(engine, corpus)
    finally:
        await engine.dispose()
    app = create_app(config)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
