"""Ownership guards and settings of the persistent local development profile (#438).

No Weaviate or network: an in-memory stand-in records what would be created or deleted,
and every refusal must leave both stores unchanged.
"""
import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import yaml

from tests import local_dev
from tests.local_dev import MARKER_COLLECTION, MARKER_PURPOSE, MARKER_TABLE, Profile, Refused
from tests.weaviate_store import MARKER_COLLECTION as TEST_MARKER_COLLECTION, MARKER_PURPOSE as TEST_MARKER_PURPOSE


class _Collection:
    def __init__(self, store: "_Client", name: str):
        self.store, self.name = store, name
        self.query = SimpleNamespace(fetch_objects=self._fetch)
        self.data = SimpleNamespace(update=self._update, insert=self._insert)
        self.config = SimpleNamespace(get=self._config)
        self.aggregate = SimpleNamespace(over_all=self._count)
        self.tenants = SimpleNamespace(get=self._tenants)

    async def _fetch(self, limit):
        return SimpleNamespace(objects=[SimpleNamespace(uuid=f"{self.name}-{i}", properties=p)
                                        for i, p in enumerate(self.store.objects[self.name][:limit])])

    async def _update(self, uuid, properties):
        self.store.writes.append(("update", self.name, properties))
        self.store.objects[self.name][int(uuid.rsplit("-", 1)[1])] = properties

    async def _insert(self, properties):
        self.store.writes.append(("insert", self.name, properties))
        self.store.objects[self.name].append(properties)

    async def _config(self):
        return SimpleNamespace(multi_tenancy_config=SimpleNamespace(enabled=False))

    async def _count(self, total_count):
        return SimpleNamespace(total_count=len(self.store.objects[self.name]))

    async def _tenants(self):
        return {}


class _Client:
    """The part of the Weaviate client the ownership checks and the reset use."""

    def __init__(self, objects: dict[str, list[dict]]):
        self.objects = objects
        self.writes: list[tuple] = []
        self.closed = False
        self.collections = SimpleNamespace(list_all=self._list_all, get=lambda name: _Collection(self, name),
                                           delete=self._delete, exists=self._exists, create=self._create)

    async def _list_all(self, simple):
        return {name: None for name in self.objects}

    async def _delete(self, name):
        self.writes.append(("delete", name))
        del self.objects[name]

    async def _exists(self, name):
        return name in self.objects

    async def _create(self, name, properties):
        self.writes.append(("create", name))
        self.objects[name] = []

    async def close(self):
        self.closed = True


def _dev_marker(token="t1", state=local_dev.READY):
    return {"purpose": MARKER_PURPOSE, "token": token, "state": state, "corpus": "x"}


def _sqlite(path, token="t1", purpose=MARKER_PURPOSE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE user (id TEXT, username TEXT)')
        if token is not None:
            db.execute(f"CREATE TABLE {MARKER_TABLE} (purpose TEXT, token TEXT)")
            db.execute(f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)", (purpose, token))
    return path


@pytest.fixture
def profile(tmp_path):
    return Profile(data_dir=tmp_path / "dev-data")


@pytest.fixture
def use_client(monkeypatch):
    """Serve ``client`` to the commands instead of connecting; seeding must not happen."""
    def install(client):
        async def connect(profile):
            return client

        async def no_initialize(client, profile):
            client.writes.append(("initialize",))

        monkeypatch.setattr(local_dev, "connect", connect)
        monkeypatch.setattr(local_dev, "initialize", no_initialize)
        return client
    return install


# --- SQLite ownership ------------------------------------------------------------------

def test_a_missing_sqlite_file_has_no_token(profile):
    assert local_dev.sqlite_token(profile.sqlite_path) is None


def test_the_marker_token_of_a_development_database_is_read(profile):
    assert local_dev.sqlite_token(_sqlite(profile.sqlite_path, token="abc")) == "abc"


@pytest.mark.parametrize("make", [
    lambda path: _sqlite(path, token=None),                            # e.g. a copied tasks.db snapshot
    lambda path: _sqlite(path, purpose="semant-automated-tests"),
    lambda path: path.write_bytes(b"not a database at all, just bytes"),
], ids=["no-marker", "other-purpose", "not-sqlite"])
def test_a_database_without_the_development_marker_is_refused_and_never_removed(profile, make):
    profile.sqlite_path.parent.mkdir(parents=True)
    make(profile.sqlite_path)
    content = profile.sqlite_path.read_bytes()

    with pytest.raises(Refused):
        local_dev.sqlite_token(profile.sqlite_path)
    with pytest.raises(Refused):
        local_dev.remove_sqlite(profile.sqlite_path)

    assert profile.sqlite_path.read_bytes() == content


def test_removing_a_development_database_removes_its_journal_files(profile):
    path = _sqlite(profile.sqlite_path)
    wal = path.with_name(path.name + "-wal")
    wal.write_bytes(b"")

    local_dev.remove_sqlite(path)

    assert not path.exists() and not wal.exists()


def test_create_sqlite_never_overwrites_an_existing_file(profile):
    path = _sqlite(profile.sqlite_path)
    content = path.read_bytes()

    with pytest.raises(Refused):
        asyncio.run(local_dev.create_sqlite(path, corpus=None, token="new"))

    assert path.read_bytes() == content


# --- Weaviate ownership ----------------------------------------------------------------

def test_an_empty_weaviate_is_empty_and_not_owned():
    state = asyncio.run(local_dev.weaviate_state(_Client({})))

    assert state.empty and not state.owned


def test_a_development_marker_makes_the_store_owned():
    client = _Client({MARKER_COLLECTION: [_dev_marker("abc")], "Chunks": [{}]})

    state = asyncio.run(local_dev.weaviate_state(client))

    assert state.owned and state.marker["token"] == "abc" and state.collections == ["Chunks"]


@pytest.mark.parametrize("objects", [
    {"Chunks": [{}], "Documents": [{}]},                                           # a snapshot
    {TEST_MARKER_COLLECTION: [{"purpose": TEST_MARKER_PURPOSE, "token": "run"}], "Chunks": []},  # a test store
    {MARKER_COLLECTION: [{"purpose": "something-else", "token": "x"}], "Chunks": []},
    {MARKER_COLLECTION: [_dev_marker("a"), _dev_marker("b")]},
], ids=["snapshot", "test-store", "foreign-marker", "two-markers"])
def test_data_without_a_single_development_marker_is_refused(objects):
    with pytest.raises(Refused):
        asyncio.run(local_dev.weaviate_state(_Client(objects)))


# --- Commands --------------------------------------------------------------------------

@pytest.mark.parametrize("objects", [
    {"Chunks": [{}], "Documents": [{}]},
    {TEST_MARKER_COLLECTION: [{"purpose": TEST_MARKER_PURPOSE, "token": "run"}], "Chunks": [{}]},
], ids=["snapshot", "test-store"])
def test_reset_refuses_a_foreign_weaviate_without_changing_either_store(profile, use_client, objects):
    client = use_client(_Client(objects))
    _sqlite(profile.sqlite_path)

    with pytest.raises(Refused):
        asyncio.run(local_dev.cmd_reset(profile, yes=True))

    assert client.writes == []
    assert local_dev.sqlite_token(profile.sqlite_path) == "t1"


def test_reset_refuses_a_foreign_sqlite_file_before_dropping_anything(profile, use_client):
    client = use_client(_Client({MARKER_COLLECTION: [_dev_marker()], "Chunks": [{}]}))
    _sqlite(profile.sqlite_path, token=None)

    with pytest.raises(Refused):
        asyncio.run(local_dev.cmd_reset(profile, yes=True))

    assert client.writes == []
    assert profile.sqlite_path.exists()


# Another checkout's Weaviate (the volume is machine-wide, .dev-data/ is per checkout) or a
# database left without its Weaviate: refused even when confirmed, before the dry-run plan.
UNPAIRED = pytest.mark.parametrize("marker, sqlite_token, message", [
    (_dev_marker("abc"), None, "is missing"),
    (_dev_marker("abc"), "other", "not the same development pair"),
    (_dev_marker("abc", local_dev.INITIALIZING), "other", "not the same development pair"),
    (None, "abc", "Weaviate is empty"),
], ids=["no-sqlite", "other-token", "partial-other-token", "sqlite-without-weaviate"])


@UNPAIRED
@pytest.mark.parametrize("yes", [True, False], ids=["confirmed", "dry-run"])
def test_reset_refuses_an_unpaired_store_without_changing_either(profile, use_client, marker, sqlite_token,
                                                                message, yes):
    client = use_client(_Client({MARKER_COLLECTION: [marker], "Chunks": [{}]} if marker else {}))
    if sqlite_token:
        _sqlite(profile.sqlite_path, token=sqlite_token)
    feedback = profile.data_dir / "feedback.log.jsonl"
    feedback.parent.mkdir(parents=True, exist_ok=True)
    feedback.write_text("{}\n")
    before = profile.sqlite_path.read_bytes() if sqlite_token else None

    with pytest.raises(Refused, match=message):
        asyncio.run(local_dev.cmd_reset(profile, yes=yes))

    assert client.writes == []
    assert (profile.sqlite_path.read_bytes() if sqlite_token else None) == before
    assert not sqlite_token or local_dev.sqlite_token(profile.sqlite_path) == sqlite_token
    assert feedback.read_text() == "{}\n"


@pytest.mark.parametrize("marker, sqlite_token", [
    (None, None),                                              # nothing yet
    (_dev_marker("abc", local_dev.INITIALIZING), None),        # interrupted before the SQLite file
    (_dev_marker("abc", local_dev.INITIALIZING), "abc"),       # interrupted reset or late initialization
], ids=["empty", "partial-no-sqlite", "partial-paired"])
def test_reset_recovers_an_empty_or_interrupted_pair(profile, use_client, marker, sqlite_token):
    client = use_client(_Client({MARKER_COLLECTION: [marker], "Chunks": [{}]} if marker else {}))
    if sqlite_token:
        _sqlite(profile.sqlite_path, token=sqlite_token)

    assert asyncio.run(local_dev.cmd_reset(profile, yes=True)) == 0

    assert client.writes[-1] == ("initialize",)
    assert not profile.sqlite_path.exists()


@UNPAIRED
def test_verify_refuses_an_unpaired_store(profile, use_client, monkeypatch, marker, sqlite_token, message):
    client = use_client(_Client({MARKER_COLLECTION: [marker], "Chunks": [{}]} if marker else {}))
    if sqlite_token:
        _sqlite(profile.sqlite_path, token=sqlite_token)
    monkeypatch.setattr(local_dev, "verify", lambda *args: pytest.fail("compared unpaired stores"))

    with pytest.raises(Refused, match=message):
        asyncio.run(local_dev.cmd_verify(profile))

    assert client.writes == []


def test_reset_without_confirmation_changes_nothing(profile, use_client):
    client = use_client(_Client({MARKER_COLLECTION: [_dev_marker()], "Chunks": [{}]}))
    _sqlite(profile.sqlite_path)

    assert asyncio.run(local_dev.cmd_reset(profile, yes=False)) == 0

    assert client.writes == []
    assert profile.sqlite_path.exists()


def test_a_confirmed_reset_marks_the_store_first_then_drops_everything_and_reseeds(profile, use_client):
    client = use_client(_Client({MARKER_COLLECTION: [_dev_marker()], "Chunks": [{}], "MyExperiment": [{}]}))
    _sqlite(profile.sqlite_path)
    (profile.data_dir / "feedback.log.jsonl").write_text("{}\n")
    keep = profile.data_dir / "notes.txt"
    keep.write_text("mine")

    assert asyncio.run(local_dev.cmd_reset(profile, yes=True)) == 0

    assert client.writes[0][0] == "update" and client.writes[0][2]["state"] == local_dev.INITIALIZING
    assert client.writes[1:] == [("delete", "Chunks"), ("delete", "MyExperiment"), ("delete", MARKER_COLLECTION),
                                 ("initialize",)]
    assert not profile.sqlite_path.exists() and not (profile.data_dir / "feedback.log.jsonl").exists()
    assert keep.read_text() == "mine"


def test_init_seeds_only_an_empty_store_pair(profile, use_client):
    client = use_client(_Client({}))

    assert asyncio.run(local_dev.cmd_init(profile)) == 0

    assert client.writes == [("initialize",)]


def test_init_keeps_an_initialized_pair(profile, use_client):
    client = use_client(_Client({MARKER_COLLECTION: [_dev_marker("abc")], "Chunks": [{}]}))
    _sqlite(profile.sqlite_path, token="abc")

    assert asyncio.run(local_dev.cmd_init(profile)) == 0

    assert client.writes == []


def test_check_does_not_initialize_an_empty_store(profile, use_client):
    client = use_client(_Client({}))

    with pytest.raises(Refused, match="not initialized"):
        asyncio.run(local_dev.cmd_init(profile, initialize_empty=False))

    assert client.writes == []


@pytest.mark.parametrize("marker, sqlite_token, message", [
    (None, "abc", "Weaviate is empty"),                                    # volume removed, SQLite kept
    (_dev_marker("abc", local_dev.INITIALIZING), "abc", "did not finish"),  # interrupted init or reset
    (_dev_marker("abc", local_dev.INITIALIZING), None, "did not finish"),   # interrupted before SQLite
    (_dev_marker("abc"), None, "is missing"),
    (_dev_marker("abc"), "other", "not the same development pair"),
], ids=["empty-weaviate", "partial", "partial-no-sqlite", "no-sqlite", "unpaired"])
def test_init_refuses_an_inconsistent_pair_without_writing(profile, use_client, marker, sqlite_token, message):
    client = use_client(_Client({MARKER_COLLECTION: [marker], "Chunks": [{}]} if marker else {}))
    if sqlite_token:
        _sqlite(profile.sqlite_path, token=sqlite_token)

    with pytest.raises(Refused, match=message):
        asyncio.run(local_dev.cmd_init(profile))

    assert client.writes == []


def test_main_reports_a_refusal_with_its_own_exit_code(profile, use_client, monkeypatch, capsys):
    use_client(_Client({"Chunks": [{}]}))
    monkeypatch.setattr(local_dev.Profile, "from_env", classmethod(lambda cls: profile))

    assert local_dev.main(["reset", "--yes"]) == 3

    assert "refused" in capsys.readouterr().err


# --- Backend settings ------------------------------------------------------------------

def test_the_backend_uses_the_development_stores_and_only_loopback_fake_providers(profile):
    environ = local_dev.backend_environ(profile)

    assert environ["SQL_DB_URL"] == f"sqlite+aiosqlite:///{profile.sqlite_path}"
    assert (environ["WEAVIATE_HOST"], environ["WEAVIATE_REST_PORT"]) == ("127.0.0.1", str(profile.rest_port))
    fake = f"http://127.0.0.1:{profile.provider_port}"
    assert environ["TOPICER_URL"] == fake
    assert environ["OPENAI_API_URL"].startswith(fake) and environ["OLLAMA_URLS"].startswith(fake)
    assert (environ["EMBEDDING_SERVICE_HOST"], environ["EMBEDDING_SERVICE_PORT"]) == ("127.0.0.1",
                                                                                     str(profile.provider_port))
    assert environ["GOOGLE_API_KEY"] == "" and environ["FEEDBACK_WEBHOOK_URL"] == ""
    # No model tier or search vector keeps an endpoint of its own.
    tiers = yaml.safe_load(open(environ["LLM_MODELS_CONFIG"]))["tiers"]
    assert all("base_url" not in tier for tier in tiers.values())
    vectors = yaml.safe_load(open(environ["SEARCH_VECTORS_CONFIG"]))["vectors"]
    assert all(urlparse(v["embedding"].get("base_url", fake)).hostname == "127.0.0.1" for v in vectors)
    # Neither does the annotation vector (#328), whatever the deployed default is.
    annotation_vector = yaml.safe_load(open(environ["ANNOTATION_VECTOR_CONFIG"]))
    assert urlparse(annotation_vector["embedding"].get("base_url", fake)).hostname == "127.0.0.1"


def test_the_development_rag_configurations_never_search_the_web(profile):
    rag_dir = local_dev.backend_environ(profile)["RAG_CONFIGS_PATH"]

    configs = [yaml.safe_load(p.read_text()) for p in sorted(Path(rag_dir).glob("*.yaml"))]

    assert configs and not any(c.get("params", {}).get("web_search_enabled") for c in configs)

