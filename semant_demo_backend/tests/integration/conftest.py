"""Fixtures for tests against a real, test-owned Weaviate (``make test-integration``).

Tests in this package must carry ``pytestmark = pytest.mark.integration``. A missing or
unowned store is an error, not a skip, so a required integration run cannot pass
without exercising Weaviate.
"""
from contextlib import asynccontextmanager

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from weaviate.classes.query import QueryReference
from weaviate.collections.data.async_ import _DataCollectionAsync

from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.config import Config
from semant_demo.main import create_app
from semant_demo.routes import ai_assistance_routes
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
from tests.app_support import make_test_config
from tests.auth_support import auth_headers
from tests.corpus import load_corpus
from tests.fake_providers import create_fake_provider_app
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
def store_token(store_endpoint) -> str:
    return store_endpoint.token


@pytest.fixture
async def weaviate_client(store_endpoint):
    client = await connect(store_endpoint)
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
async def seeded_store(weaviate_client, collection_names, corpus, store_token):
    """Fresh application collections holding the fixture corpus; dropped afterwards."""
    # Also removes leftovers of an interrupted earlier test in this owned instance.
    await drop_app_collections(weaviate_client, collection_names, store_token)
    await create_app_schema(weaviate_client, collection_names)
    await seed_weaviate(weaviate_client, collection_names, corpus, store_token)
    try:
        yield weaviate_client
    finally:
        await drop_app_collections(weaviate_client, collection_names, store_token)


@pytest.fixture
def searcher(seeded_store, collection_names) -> WeaviateAbstraction:
    """Transitional facade, for adapters that have not moved to ``adapters/weaviate`` yet."""
    return WeaviateAbstraction(seeded_store, collection_names)


@pytest.fixture
def collections(seeded_store, collection_names) -> UserCollectionRepository:
    return UserCollectionRepository(seeded_store, collection_names)


@pytest.fixture
def documents(seeded_store, collection_names) -> DocumentRepository:
    return DocumentRepository(seeded_store, collection_names)


@pytest.fixture
def tags(seeded_store, collection_names) -> TagRepository:
    return TagRepository(seeded_store, collection_names)


@pytest.fixture
def spans(seeded_store, collection_names) -> SpanRepository:
    return SpanRepository(seeded_store, collection_names)


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
        # Unhandled server errors become 500 responses, as a real client would see them.
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
def fail_writes(monkeypatch):
    """Make selected real Weaviate writes fail (or silently do nothing).

    ``fail_writes("reference_add", ids)`` fails ``reference_add`` calls whose source object
    is in ``ids``; other calls reach Weaviate unchanged. ``collection=`` limits it to one
    collection (for ``insert``, which has no source id), ``error=`` sets the exception and
    ``no_op=True`` returns success without writing.
    """
    def install(method, ids=None, *, collection=None, error=None, no_op=False):
        original = getattr(_DataCollectionAsync, method)
        failing = None if ids is None else {str(i) for i in ids}
        calls = []

        async def wrapper(self, *args, **kwargs):
            target = kwargs.get("from_uuid", kwargs.get("uuid", args[0] if args else None))
            if (collection is None or self.name == collection) and (failing is None or str(target) in failing):
                calls.append(str(target))
                if no_op:
                    return True
                raise error or RuntimeError("injected write failure")
            return await original(self, *args, **kwargs)

        monkeypatch.setattr(_DataCollectionAsync, method, wrapper)
        return calls
    return install


@pytest.fixture
def fake_topicer(monkeypatch, corpus):
    """Route AI suggestion calls to the deterministic fake Topicer and record them."""
    calls = []
    app = create_fake_provider_app(corpus)

    @asynccontextmanager
    async def client():
        calls.append("topicer")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fake-topicer") as c:
            yield c

    monkeypatch.setattr(ai_assistance_routes, "topicer_client", client)
    return calls


@pytest.fixture
def login(api_client, corpus):
    async def headers(user):
        if user is None:
            return {}
        u = corpus.users[user]
        return await auth_headers(api_client, u["username"], u["password"])
    return headers


@pytest.fixture
def ids(corpus):
    class Ids:
        col = {k: v["id"] for k, v in corpus.collections.items()}
        doc = {k: v["id"] for k, v in corpus.documents.items()}
        chunk = {k: v["id"] for k, v in corpus.chunks.items()}
        tag = {k: v["id"] for k, v in corpus.tags.items()}
        span = {k: v["id"] for k, v in corpus.spans.items()}
        user = {k: v["id"] for k, v in corpus.users.items()}
    return Ids


@pytest.fixture
def store(seeded_store, collection_names):
    """Read-back helpers for asserting what was (not) written."""
    names = collection_names

    class Store:
        async def collections_of_chunk(self, chunk_id):
            obj = await seeded_store.collections.get(names.chunks_collection_name).query.fetch_object_by_id(
                chunk_id, return_references=[QueryReference(link_on=names.user_collection_link_name)])
            refs = obj.references.get(names.user_collection_link_name) if obj.references else None
            return {str(r.uuid) for r in (refs.objects if refs else [])}

        async def collections_of_document(self, document_id):
            obj = await seeded_store.collections.get(names.document_collection_name).query.fetch_object_by_id(
                document_id, return_references=[QueryReference(link_on="collection")])
            refs = obj.references.get("collection") if obj.references else None
            return [str(r.uuid) for r in (refs.objects if refs else [])]

        async def span(self, span_id):
            obj = await seeded_store.collections.get(names.span_collection_name).query.fetch_object_by_id(span_id)
            return obj.properties if obj else None

        async def span_count(self):
            agg = await seeded_store.collections.get(names.span_collection_name).aggregate.over_all(total_count=True)
            return agg.total_count

        async def tag(self, tag_id):
            obj = await seeded_store.collections.get(names.tag_collection_name).query.fetch_object_by_id(tag_id)
            return obj.properties if obj else None

        async def collection(self, collection_id):
            obj = await seeded_store.collections.get(names.user_collection_name).query.fetch_object_by_id(collection_id)
            return obj.properties if obj else None
    return Store()
