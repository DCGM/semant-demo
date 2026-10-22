"""Persistent local development profile (#438): a seeded Weaviate and SQLite pair that
survives restarts, fake AI providers and the backend settings that use them.

Normally run through ``scripts/local-dev.sh`` (``make dev-up``, ``dev-backend``,
``dev-reset``, ...), which starts the dedicated Weaviate container and checks that it is
the one listening on the configured port. From ``semant_demo_backend``::

    python -m tests.local_dev init             initialize an empty store pair; verify, never reseed, an initialized one
    python -m tests.local_dev check            fail unless the stores are an initialized pair (read-only)
    python -m tests.local_dev status           what the stores hold (read-only)
    python -m tests.local_dev verify           compare the stores with the seeded corpus (read-only)
    python -m tests.local_dev reset [--yes]    show what would be destroyed; with --yes drop it and reseed
    python -m tests.local_dev add-documents --count N [--no-outliers]
                                               add synthetic metadata-only documents (tests/synthetic_documents.py)
    python -m tests.local_dev environ          shell exports of the backend settings
    python -m tests.local_dev providers        serve the fake AI providers

The stores hold the synthetic fixture corpus (``tests/fixtures/corpus.json``, the same as
the integration and browser tests) with its users, collections, documents, chunks, tags
and annotations, search vectors and derived annotation data from the fake embedder.

Ownership. The pair is paired by a random token that ``init`` writes into both stores: the
``SemantLocalDevMarker`` collection in Weaviate and the ``semant_local_dev_marker`` table in
SQLite. It differs from the automated-test marker (``tests/weaviate_store.py``), so neither
tooling accepts the other's store. ``init`` writes only into an empty Weaviate with no
SQLite file; ``reset`` drops data only from a pair with the same token (or an interrupted
initialization that has not created its SQLite file yet) and refuses anything else, e.g. a
snapshot, a test store, another checkout's Weaviate or an unpaired SQLite file. The Docker
volume is machine-wide while ``.dev-data/`` belongs to a checkout, so an unpaired store may
hold someone's work: it is never discarded automatically. Weaviate is reached
on loopback only; the SQLite file is always ``.dev-data/semant.db`` of this checkout,
never ``local_data/``.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import secrets
import shlex
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "semant_demo_backend"
DATA_DIR = ROOT / ".dev-data"
SQLITE_NAME = "semant.db"

HOST = "127.0.0.1"
DEFAULT_WEAVIATE_REST_PORT = 8180
DEFAULT_WEAVIATE_GRPC_PORT = 50151
DEFAULT_PROVIDER_PORT = 8009
ENV_REST_PORT = "SEMANT_DEV_WEAVIATE_REST_PORT"
ENV_GRPC_PORT = "SEMANT_DEV_WEAVIATE_GRPC_PORT"
ENV_PROVIDER_PORT = "SEMANT_DEV_PROVIDER_PORT"

MARKER_COLLECTION = "SemantLocalDevMarker"
MARKER_TABLE = "semant_local_dev_marker"
MARKER_PURPOSE = "semant-local-development"
READY, INITIALIZING = "ready", "initializing"

# Development only: the stores are on loopback and hold synthetic data.
DEV_JWT_SECRET = "local-development-only-secret-not-for-any-deployment"
FRONTEND_ORIGIN = "http://localhost:9000"
# Seconds between streamed Topicer chunks, so a suggestion run is visibly incremental.
FAKE_TOPICER_STREAM_DELAY = 0.5


class Refused(RuntimeError):
    """The stores are not (or not consistently) the development pair; nothing was changed."""


@dataclass(frozen=True)
class Profile:
    data_dir: Path = DATA_DIR
    rest_port: int = DEFAULT_WEAVIATE_REST_PORT
    grpc_port: int = DEFAULT_WEAVIATE_GRPC_PORT
    provider_port: int = DEFAULT_PROVIDER_PORT

    @classmethod
    def from_env(cls) -> "Profile":
        return cls(rest_port=int(os.environ.get(ENV_REST_PORT, DEFAULT_WEAVIATE_REST_PORT)),
                   grpc_port=int(os.environ.get(ENV_GRPC_PORT, DEFAULT_WEAVIATE_GRPC_PORT)),
                   provider_port=int(os.environ.get(ENV_PROVIDER_PORT, DEFAULT_PROVIDER_PORT)))

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / SQLITE_NAME

    @property
    def provider_url(self) -> str:
        return f"http://{HOST}:{self.provider_port}"

    @property
    def endpoint(self) -> str:
        return f"{HOST}:{self.rest_port} (gRPC {self.grpc_port})"


def corpus_digest() -> str:
    from tests.corpus import CORPUS_PATH
    return hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()[:16]


# --- Backend settings -------------------------------------------------------------------

def backend_environ(profile: Profile) -> dict[str, str]:
    """The settings of a backend on the development stores and fake providers. Writes the
    derived configuration files into ``<data_dir>/config`` (regenerated on every call)."""
    from tests.fake_providers import fake_provider_environ

    config_dir = profile.data_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return {
        "WEAVIATE_HOST": HOST,
        "WEAVIATE_REST_PORT": str(profile.rest_port),
        "WEAVIATE_GRPC_PORT": str(profile.grpc_port),
        "SQL_DB_URL": f"sqlite+aiosqlite:///{profile.sqlite_path}",
        **fake_provider_environ(config_dir, profile.provider_url, profile.provider_port),
        "RAG_CONFIGS_PATH": str(write_rag_configs(config_dir / "rag")),
        "JWT_SECRET": DEV_JWT_SECRET,
        "ALLOWED_ORIGIN": FRONTEND_ORIGIN,
        "FEEDBACK_LOG_PATH": str(profile.data_dir / "feedback.log.jsonl"),
        "FEEDBACK_WEBHOOK_URL": "",
        "PRODUCTION": "false",
        "OTEL_ENABLED": "false",
        "DEPLOYMENT_ENVIRONMENT": "local-development",
    }


def write_rag_configs(rag_dir: Path) -> Path:
    """The demo RAG configurations with web search off: it would query a live search
    engine, which the fake providers do not replace."""
    source = BACKEND / "semant_demo" / "configs" / "rag" / "demo_configs"
    rag_dir.mkdir(parents=True, exist_ok=True)
    for old in rag_dir.glob("*.yaml"):
        old.unlink()
    for path in sorted(source.glob("*.yaml")):
        config = yaml.safe_load(path.read_text())
        params = config.setdefault("params", {})
        if params.get("web_search_enabled"):
            params["web_search_enabled"] = False
        (rag_dir / path.name).write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))
    return rag_dir


# --- SQLite ---------------------------------------------------------------------------

def sqlite_token(path: Path) -> str | None:
    """The development token of the SQLite file at ``path``; ``None`` when it does not exist.
    Raises ``Refused`` for a file without the development marker."""
    if not path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            rows = db.execute(f"SELECT purpose, token FROM {MARKER_TABLE}").fetchall()
    except sqlite3.Error as e:
        raise Refused(f"{path} exists but is not a development database ({e}). Move it away yourself "
                      "if it is not needed; it is never deleted automatically.") from e
    tokens = [token for purpose, token in rows if purpose == MARKER_PURPOSE]
    if len(tokens) != 1:
        raise Refused(f"{path} has no valid development marker; it is never deleted automatically.")
    return tokens[0]


def _sqlite_files(path: Path) -> list[Path]:
    return [path, *(path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal"))]


def remove_sqlite(path: Path) -> None:
    """Delete the development SQLite file at ``path`` after re-checking its marker."""
    if sqlite_token(path) is None:
        return
    for file in _sqlite_files(path):
        file.unlink(missing_ok=True)


async def create_sqlite(path: Path, corpus, token: str) -> None:
    """Create the SQLite database with the corpus users and the marker. It is written to a
    temporary file first, so an interrupted run leaves no half-initialized database."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.seed import seed_users

    if path.exists():
        raise Refused(f"{path} already exists; not overwriting it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".initializing")
    for file in _sqlite_files(partial):
        file.unlink(missing_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{partial}")
    try:
        await seed_users(engine, corpus)
    finally:
        await engine.dispose()
    with sqlite3.connect(partial) as db:
        db.execute(f"CREATE TABLE {MARKER_TABLE} (purpose TEXT NOT NULL, token TEXT NOT NULL)")
        db.execute(f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)", (MARKER_PURPOSE, token))
    os.replace(partial, path)


def sqlite_users(path: Path) -> dict[str, str]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        return {str(UUID(row[0])): row[1] for row in db.execute("SELECT id, username FROM user")}


# --- Weaviate -------------------------------------------------------------------------

@dataclass
class WeaviateState:
    collections: list[str]
    marker: dict | None = None

    @property
    def empty(self) -> bool:
        return not self.collections

    @property
    def owned(self) -> bool:
        return self.marker is not None


async def connect(profile: Profile):
    from tests.weaviate_store import StoreEndpoint, connect as connect_store

    return await connect_store(StoreEndpoint(HOST, profile.rest_port, profile.grpc_port, token=""))


async def weaviate_state(client) -> WeaviateState:
    """What the instance holds. Raises ``Refused`` for data without the development marker
    (a snapshot, an automated-test store, ...)."""
    names = sorted((await client.collections.list_all(simple=True)).keys())
    state = WeaviateState(collections=[n for n in names if n != MARKER_COLLECTION])
    if MARKER_COLLECTION not in names:
        if state.collections:
            raise Refused(
                "This Weaviate holds data without the local development marker (collections: "
                f"{', '.join(state.collections)}). It is not the development store; refusing to use it.")
        return state
    objects = (await client.collections.get(MARKER_COLLECTION).query.fetch_objects(limit=10)).objects
    markers = [{**o.properties, "uuid": o.uuid} for o in objects if o.properties.get("purpose") == MARKER_PURPOSE]
    if len(markers) != 1:
        raise Refused(f"{MARKER_COLLECTION} exists but holds no single development marker; refusing to use it.")
    state.marker = markers[0]
    return state


async def write_marker(client, token: str, status: str) -> None:
    from weaviate.classes.config import DataType, Property

    if not await client.collections.exists(MARKER_COLLECTION):
        await client.collections.create(MARKER_COLLECTION, properties=[
            Property(name=name, data_type=DataType.TEXT) for name in ("purpose", "token", "state", "corpus")])
    marker = client.collections.get(MARKER_COLLECTION)
    existing = (await marker.query.fetch_objects(limit=10)).objects
    properties = {"purpose": MARKER_PURPOSE, "token": token, "state": status, "corpus": corpus_digest()}
    if existing:
        await marker.data.update(uuid=existing[0].uuid, properties=properties)
    else:
        await marker.data.insert(properties)


async def derive_annotations(client, profile: Profile, corpus) -> None:
    """Store the annotations' derived text, positions and contextual vectors (#328) as the
    backend would, with the fake embedder called in-process."""
    from semant_demo.config import Config
    from tests.seed import derive_annotations as derive

    await derive(client, Config(environ=backend_environ(profile)), corpus)


async def seed_weaviate(client, profile: Profile, corpus) -> None:
    from semant_demo.config import Config
    from tests.seed import insert_corpus
    from tests.weaviate_store import create_app_schema

    names = Config(environ={}).collectionNames
    await create_app_schema(client, names)
    await insert_corpus(client, names, corpus)
    await derive_annotations(client, profile, corpus)


# --- Pairing --------------------------------------------------------------------------

def pairing_refusal(state: WeaviateState, token: str | None, path: Path) -> str | None:
    """Why Weaviate and the SQLite file at ``path`` are not one development pair of this
    checkout; ``None`` when they are: both empty, the same token, or an interrupted
    initialization (marker ``initializing``, no SQLite file created yet). Only such a pair
    may be initialized, used or reset from here."""
    discard = ("To discard the development Weaviate deliberately: make dev-down && "
               "docker volume rm semant-local-weaviate, then make dev-up.")
    if not state.owned:
        if token is None:
            return None
        return (f"Weaviate is empty but {path} exists (its Weaviate volume was removed?). The unpaired "
                "database may hold accounts you registered and is never deleted automatically; move it "
                "away yourself (e.g. mv .dev-data/semant.db .dev-data/semant.db.unpaired), then make dev-up.")
    if token == state.marker["token"]:
        return None
    if token is None and state.marker["state"] == INITIALIZING:
        return None
    if token is None:
        return (f"Weaviate holds an initialized development store but {path} is missing: the store belongs "
                "to another checkout's .dev-data/, or this checkout's .dev-data/ was removed. Nothing is "
                "changed from here; use the checkout that owns it. " + discard)
    return (f"Weaviate and {path} are not the same development pair (SQLite from another initialization, "
            "e.g. the Weaviate belongs to another checkout). Nothing is changed from here; use the checkout "
            "that owns the Weaviate data. " + discard)


# --- Commands -------------------------------------------------------------------------

def _say(message: str) -> None:
    print(f"local-dev: {message}", file=sys.stderr)


async def initialize(client, profile: Profile) -> None:
    """Seed an empty Weaviate and a missing SQLite file. The marker comes first, in state
    ``initializing``, and becomes ``ready`` only after both stores are complete."""
    from tests.corpus import load_corpus

    corpus = load_corpus()
    token = secrets.token_hex(16)
    _say(f"initializing the development stores: Weaviate {profile.endpoint}, SQLite {profile.sqlite_path}")
    await write_marker(client, token, INITIALIZING)
    await seed_weaviate(client, profile, corpus)
    await create_sqlite(profile.sqlite_path, corpus, token)
    await write_marker(client, token, READY)
    problems = await verify(client, profile)
    if problems:
        raise RuntimeError("The seeded stores do not match the corpus:\n  " + "\n  ".join(problems))
    _say("initialized with the fixture corpus and verified")


async def cmd_init(profile: Profile, initialize_empty: bool = True) -> int:
    """Initialize empty stores (unless ``initialize_empty`` is false: ``check``); otherwise
    verify that they are a completely initialized pair, without changing them."""
    client = await connect(profile)
    try:
        state = await weaviate_state(client)
        token = sqlite_token(profile.sqlite_path)
        if problem := pairing_refusal(state, token, profile.sqlite_path):
            raise Refused(problem)
        if not state.owned:
            if not initialize_empty:
                raise Refused("The development stores are not initialized; run: make dev-up")
            await initialize(client, profile)
            return 0
        _require_ready(state)
        if initialize_empty:
            _say("the development stores are initialized; keeping their data (make dev-reset reseeds)")
        return 0
    finally:
        await client.close()


def _require_ready(state: WeaviateState) -> None:
    if state.marker["state"] != READY:
        raise Refused("A previous initialization or reset did not finish (marker state "
                      f"{state.marker['state']!r}). Start again with: make dev-reset")


async def _counts(client, state: WeaviateState) -> list[str]:
    lines = []
    for name in state.collections:
        collection = client.collections.get(name)
        if (await collection.config.get()).multi_tenancy_config.enabled:
            lines.append(f"{name}: {len(await collection.tenants.get())} tenants")
        else:
            lines.append(f"{name}: {(await collection.aggregate.over_all(total_count=True)).total_count} objects")
    return lines


async def cmd_status(profile: Profile) -> int:
    client = await connect(profile)
    try:
        state = await weaviate_state(client)
        print(f"Weaviate {profile.endpoint}: " + (
            "empty (make dev-up initializes it)" if state.empty and not state.owned else
            f"development store, marker state {state.marker['state']!r}"))
        for line in await _counts(client, state):
            print(f"  {line}")
        token = sqlite_token(profile.sqlite_path)
        print(f"SQLite {profile.sqlite_path}: " + (
            "missing" if token is None else
            f"{len(sqlite_users(profile.sqlite_path))} users, "
            + ("paired with this Weaviate" if state.owned and token == state.marker["token"] else
               "NOT paired with this Weaviate (make dev-reset)")))
        return 0
    finally:
        await client.close()


async def _ids(collection, tenant: str | None = None) -> set[str]:
    if tenant is not None:
        collection = collection.with_tenant(tenant)
    return {str(o.uuid) async for o in collection.iterator()}


async def verify(client, profile: Profile) -> list[str]:
    """Differences between the stores and the seeded corpus (empty: they match). Compares
    identities and ownership, not every property."""
    from semant_demo.config import Config
    from tests.corpus import load_corpus
    from tests.synthetic_documents import is_synthetic

    corpus, names = load_corpus(), Config(environ={}).collectionNames
    problems: list[str] = []

    def compare(what: str, actual, expected) -> None:
        if actual != expected:
            problems.append(f"{what}: stored {sorted(actual) if isinstance(actual, set) else actual}, "
                            f"seeded {sorted(expected) if isinstance(expected, set) else expected}")

    users = {u["id"]: u for u in corpus.users.values()}
    compare("SQLite users", sqlite_users(profile.sqlite_path), {i: u["username"] for i, u in users.items()})
    collections = client.collections.get(names.user_collection_name)
    stored = {str(o.uuid): (o.properties["user_id"], sorted(str(u) for u in o.properties.get("shared_with") or []))
              async for o in collections.iterator()}
    compare("collection owners and shares", stored, {
        c["id"]: (corpus.users[c["owner"]]["id"], sorted(corpus.users[u]["id"] for u in c["shared_with"]))
        for c in corpus.collections.values()})
    compare("tags", await _ids(client.collections.get(names.tag_collection_name)),
            {t["id"] for t in corpus.tags.values()})
    stored_documents = await _ids(client.collections.get(names.document_collection_name))
    compare("documents", {i for i in stored_documents if not is_synthetic(i)}, {d["id"] for d in corpus.documents.values()})
    if synthetic := sum(map(is_synthetic, stored_documents)):
        problems.append(f"documents: {synthetic} synthetic documents added (make dev-add-documents)")
    compare("chunks", await _ids(client.collections.get(names.chunks_collection_name)),
            {c["id"] for c in corpus.chunks.values()})
    annotations = client.collections.get(names.annotation_collection_name)
    expected: dict[str, set[str]] = {}
    for span in corpus.spans.values():
        tenant = str(UUID(corpus.collections[corpus.tags[span["tag"]]["collection"]]["id"]))
        expected.setdefault(tenant, set()).add(span["id"])
    tenants = set((await annotations.tenants.get()).keys())
    compare("annotation tenants", tenants, set(expected))
    for tenant in sorted(tenants & set(expected)):
        compare(f"annotations of {tenant}", await _ids(annotations, tenant), expected[tenant])
    return problems


async def cmd_verify(profile: Profile) -> int:
    client = await connect(profile)
    try:
        state = await weaviate_state(client)
        if problem := pairing_refusal(state, sqlite_token(profile.sqlite_path), profile.sqlite_path):
            raise Refused(problem)
        if not state.owned:
            raise Refused("The development stores are not initialized (make dev-up).")
        _require_ready(state)
        problems = await verify(client, profile)
    finally:
        await client.close()
    for problem in problems:
        print(f"differs: {problem}")
    print("the stores hold the seeded corpus" if not problems else
          f"{len(problems)} difference(s) from the seeded corpus (edits since the seed, or make dev-reset)")
    return 0 if not problems else 1


async def cmd_reset(profile: Profile, yes: bool) -> int:
    client = await connect(profile)
    try:
        # All checks before anything is deleted: either store, or their pairing, may refuse.
        state = await weaviate_state(client)
        token = sqlite_token(profile.sqlite_path)
        if problem := pairing_refusal(state, token, profile.sqlite_path):
            raise Refused(problem)
        print(f"Reset destroys the local development data and reseeds the fixture corpus:\n"
              f"  Weaviate {profile.endpoint}: "
              + (", ".join(await _counts(client, state)) if state.collections else "empty")
              + f"\n  SQLite {profile.sqlite_path}: "
              + ("missing" if token is None else f"{len(sqlite_users(profile.sqlite_path))} users and all other rows")
              + f"\n  {profile.data_dir / 'feedback.log.jsonl'}"
              + "\nNot touched: local_data/, automated-test containers, other files.", file=sys.stderr)
        if not yes:
            _say("dry run, nothing changed yet")
            return 0
        if state.owned:
            # A reset interrupted from here on leaves a store that `init` refuses.
            await write_marker(client, state.marker["token"], INITIALIZING)
        for name in state.collections:
            await client.collections.delete(name)
        remove_sqlite(profile.sqlite_path)
        (profile.data_dir / "feedback.log.jsonl").unlink(missing_ok=True)
        if state.owned:
            await client.collections.delete(MARKER_COLLECTION)
        await initialize(client, profile)
        return 0
    finally:
        await client.close()


ADD_BATCH_SIZE = 1000


async def add_documents(client, count: int, outliers: bool) -> int:
    """Insert the synthetic documents that are not stored yet and return how many were added.
    Declares ``Documents.library`` first when the store lacks it, as production has it
    (``field`` tokenization). Batches are written one after another: a failure keeps the
    earlier ones, and running again adds the rest."""
    from weaviate.classes.data import DataObject
    from weaviate.classes.query import Filter

    from semant_demo.adapters.weaviate.document_metadata import add_text_property
    from semant_demo.config import Config
    from tests.synthetic_documents import synthetic_documents

    names = Config(environ={}).collectionNames
    documents = client.collections.get(names.document_collection_name)
    if "library" not in {p.name for p in (await documents.config.get()).properties}:
        await add_text_property(client, names, "library")
        _say("declared Documents.library (text, field tokenization)")
    pending = list(synthetic_documents(count, outliers))
    added = 0
    for start in range(0, len(pending), ADD_BATCH_SIZE):
        batch = pending[start:start + ADD_BATCH_SIZE]
        stored = await documents.query.fetch_objects(
            filters=Filter.by_id().contains_any([uuid for uuid, _ in batch]), limit=len(batch), return_properties=[])
        existing = {o.uuid for o in stored.objects}
        new = [DataObject(uuid=uuid, properties=properties) for uuid, properties in batch if uuid not in existing]
        if new:
            result = await documents.data.insert_many(new)
            if result.has_errors:
                raise RuntimeError(f"Adding documents failed after {added} were added (running again adds the "
                                   f"rest): {list(result.errors.values())[:3]}")
            added += len(new)
        if len(pending) > 10 * ADD_BATCH_SIZE and (start // ADD_BATCH_SIZE) % 10 == 9:
            _say(f"{start + len(batch)} of {len(pending)} documents checked, {added} added")
    return added


async def cmd_add_documents(profile: Profile, count: int, outliers: bool) -> int:
    client = await connect(profile)
    try:
        state = await weaviate_state(client)
        if problem := pairing_refusal(state, sqlite_token(profile.sqlite_path), profile.sqlite_path):
            raise Refused(problem)
        if not state.owned:
            raise Refused("The development stores are not initialized (make dev-up).")
        _require_ready(state)
        requested = count + (2 if outliers else 0)
        added = await add_documents(client, count, outliers)
    finally:
        await client.close()
    _say(f"added {added} synthetic documents ({requested - added} of the {requested} requested were already "
         "stored); make dev-reset removes them. A running backend serves its cached corpus overview for up to "
         "CORPUS_OVERVIEW_MAX_AGE seconds (default 600); restart make dev-backend to see them at once.")
    return 0


def cmd_environ(profile: Profile) -> int:
    for key, value in backend_environ(profile).items():
        print(f"export {key}={shlex.quote(value)}")
    return 0


def cmd_providers(profile: Profile) -> int:
    import uvicorn

    from tests.corpus import load_corpus
    from tests.fake_providers import create_fake_provider_app

    _say(f"fake embedding, Topicer and LLM providers on {profile.provider_url} (unfaked routes answer 501)")
    uvicorn.run(create_fake_provider_app(load_corpus(), FAKE_TOPICER_STREAM_DELAY),
                host=HOST, port=profile.provider_port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "check", "status", "verify", "environ", "providers"):
        sub.add_parser(name)
    reset = sub.add_parser("reset")
    reset.add_argument("--yes", action="store_true", help="drop the data and reseed (otherwise a dry run)")
    add = sub.add_parser("add-documents")
    add.add_argument("--count", type=int, required=True, help="synthetic documents to have in the store")
    add.add_argument("--no-outliers", action="store_true", help="omit the documents from the years 311 and 2879")
    args = parser.parse_args(argv)
    if args.command == "add-documents":
        from tests.synthetic_documents import MAX_COUNT
        if not 0 <= args.count <= MAX_COUNT:
            parser.error(f"--count must be between 0 and {MAX_COUNT}")
    from tests.weaviate_store import StoreUnavailable

    profile = Profile.from_env()
    try:
        if args.command == "environ":
            return cmd_environ(profile)
        if args.command == "providers":
            return cmd_providers(profile)
        if args.command == "check":
            return asyncio.run(cmd_init(profile, initialize_empty=False))
        if args.command == "reset":
            return asyncio.run(cmd_reset(profile, args.yes))
        if args.command == "add-documents":
            return asyncio.run(cmd_add_documents(profile, args.count, not args.no_outliers))
        return asyncio.run({"init": cmd_init, "status": cmd_status, "verify": cmd_verify}[args.command](profile))
    except Refused as e:
        _say(f"refused: {e}")
        return 3
    except StoreUnavailable as e:
        _say(f"Weaviate {profile.endpoint} is not available; start it with make dev-up ({e})")
        return 4


if __name__ == "__main__":
    sys.exit(main())
