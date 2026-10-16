"""Safety rules of the test-owned Weaviate store, checked without a server."""
import pytest

from tests.weaviate_store import (
    MARKER_COLLECTION,
    MARKER_PURPOSE,
    StoreEndpoint,
    StoreNotOwned,
    StoreUnavailable,
    claim_store,
)

ENDPOINT_ENV = {
    "SEMANT_TEST_WEAVIATE_HOST": "127.0.0.1",
    "SEMANT_TEST_WEAVIATE_REST_PORT": "18080",
    "SEMANT_TEST_WEAVIATE_GRPC_PORT": "15051",
    "SEMANT_TEST_STORE_TOKEN": "run-a",
}
RUN_TOKEN = "run-a"
OTHER_RUN_TOKEN = "run-b"


class FakeCollection:
    def __init__(self, store, name):
        self.store, self.name = store, name
        self.data, self.query = self, self

    async def insert(self, properties):
        self.store.objects.setdefault(self.name, []).append(properties)

    async def fetch_objects(self, limit):
        class Obj:
            def __init__(self, properties):
                self.properties = properties

        class Result:
            objects = [Obj(p) for p in self.store.objects.get(self.name, [])][:limit]
        return Result()


class FakeCollections:
    """Just enough of ``client.collections`` for ``claim_store``."""

    def __init__(self, names=(), objects=None):
        self.names = set(names)
        self.objects = dict(objects or {})
        self.created = []

    async def list_all(self, simple):
        return {name: None for name in self.names}

    def get(self, name):
        return FakeCollection(self, name)

    async def create(self, name, properties):
        self.names.add(name)
        self.created.append(name)


class FakeClient:
    def __init__(self, collections):
        self.collections = collections


def test_endpoint_requires_explicit_test_settings():
    with pytest.raises(StoreUnavailable):
        StoreEndpoint.from_env({})


def test_endpoint_requires_ownership_token():
    env = {k: v for k, v in ENDPOINT_ENV.items() if k != "SEMANT_TEST_STORE_TOKEN"}

    with pytest.raises(StoreUnavailable):
        StoreEndpoint.from_env(env)


def test_endpoint_ignores_application_weaviate_settings():
    with pytest.raises(StoreUnavailable):
        StoreEndpoint.from_env({"WEAVIATE_HOST": "localhost", "WEAVIATE_REST_PORT": "8080"})


def test_endpoint_refuses_non_loopback_host():
    env = {**ENDPOINT_ENV, "SEMANT_TEST_WEAVIATE_HOST": "192.0.2.10"}

    with pytest.raises(StoreUnavailable):
        StoreEndpoint.from_env(env)


def test_endpoint_allows_explicitly_dedicated_non_loopback_host():
    env = {**ENDPOINT_ENV, "SEMANT_TEST_WEAVIATE_HOST": "192.0.2.10",
           "SEMANT_TEST_WEAVIATE_ALLOW_NONLOCAL": "1"}

    endpoint = StoreEndpoint.from_env(env)

    assert endpoint.token == RUN_TOKEN
    assert endpoint.app_environ() == {
        "WEAVIATE_HOST": "192.0.2.10", "WEAVIATE_REST_PORT": "18080", "WEAVIATE_GRPC_PORT": "15051",
    }


async def test_empty_instance_is_claimed_with_current_token():
    collections = FakeCollections()

    await claim_store(FakeClient(collections), RUN_TOKEN)

    assert collections.created == [MARKER_COLLECTION]
    assert collections.objects[MARKER_COLLECTION] == [{"purpose": MARKER_PURPOSE, "token": RUN_TOKEN}]


async def test_marker_with_matching_token_is_accepted():
    collections = FakeCollections(
        names={MARKER_COLLECTION, "Chunks"},
        objects={MARKER_COLLECTION: [{"purpose": MARKER_PURPOSE, "token": RUN_TOKEN}]},
    )

    await claim_store(FakeClient(collections), RUN_TOKEN)

    assert collections.created == []


@pytest.mark.parametrize("marker", [
    {"purpose": MARKER_PURPOSE, "token": OTHER_RUN_TOKEN},  # left by another run
    {"purpose": MARKER_PURPOSE},  # marker without a token
], ids=["other-run-token", "no-token"])
async def test_marker_from_another_run_is_refused(marker):
    collections = FakeCollections(names={MARKER_COLLECTION, "Chunks"}, objects={MARKER_COLLECTION: [marker]})

    with pytest.raises(StoreNotOwned):
        await claim_store(FakeClient(collections), RUN_TOKEN)

    assert collections.created == []


async def test_unmarked_instance_with_data_is_refused():
    collections = FakeCollections(names={"Chunks", "Documents"})

    with pytest.raises(StoreNotOwned):
        await claim_store(FakeClient(collections), RUN_TOKEN)

    assert collections.created == []


async def test_empty_token_never_claims():
    collections = FakeCollections()

    with pytest.raises(StoreNotOwned):
        await claim_store(FakeClient(collections), "")

    assert collections.created == []
