"""Write the fixture corpus into a test-owned Weaviate store and a test SQL database."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import cache
from uuid import UUID

from fastapi_users.password import PasswordHelper
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from weaviate import WeaviateAsyncClient
from weaviate.classes.data import DataObject
from weaviate.classes.tenants import Tenant

from semant_demo.adapters.sql.tables import create_tables
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.users.models import User
from tests.corpus import Corpus
from tests.fakes import SECOND_VECTOR, fake_embedding, second_embedding
from tests.weaviate_store import claim_store

FIXTURE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _insert(client: WeaviateAsyncClient, collection: str, objects: list[DataObject]) -> None:
    result = await client.collections.get(collection).data.insert_many(objects)
    if result.has_errors:
        raise RuntimeError(f"Seeding {collection} failed: {result.errors}")


async def seed_weaviate(client: WeaviateAsyncClient, names: CollectionNames, corpus: Corpus, token: str) -> None:
    """Insert the corpus into the (already created, empty) application collections of a
    test-owned store (``token``, verified first)."""
    await claim_store(client, token)
    await insert_corpus(client, names, corpus)


async def insert_corpus(client: WeaviateAsyncClient, names: CollectionNames, corpus: Corpus) -> None:
    """Insert the corpus into the (already created, empty) application collections. The
    spans go to the annotation tenants; the legacy ``Span`` collection stays empty. The
    caller has verified that it owns the store (tests: ``seed_weaviate``; the persistent
    local development store: ``tests.local_dev``)."""
    users, collections, tags, chunks = corpus.users, corpus.collections, corpus.tags, corpus.chunks

    await _insert(client, names.user_collection_name, [
        DataObject(uuid=col["id"], properties={
            "name": col["name"],
            "description": col["description"],
            "color": col["color"],
            "owner": users[col["owner"]]["name"],
            "user_id": users[col["owner"]]["id"],
            "shared_with": [users[u]["id"] for u in col["shared_with"]],
            "created_at": FIXTURE_TIMESTAMP,
            "updated_at": FIXTURE_TIMESTAMP,
        })
        for col in collections.values()
    ])
    await _insert(client, names.tag_collection_name, [
        DataObject(
            uuid=tag["id"],
            properties={
                "tag_name": tag["name"],
                "tag_shorthand": tag["shorthand"],
                "tag_color": tag["color"],
                "tag_pictogram": tag["pictogram"],
                "tag_definition": tag["definition"],
                "tag_examples": tag["examples"],
            },
            references={"userCollection": collections[tag["collection"]]["id"]},
        )
        for tag in tags.values()
    ])
    await _insert(client, names.document_collection_name, [
        DataObject(
            uuid=doc["id"],
            properties=doc["properties"],
            references={"collection": [collections[c]["id"] for c in doc["collections"]]},
        )
        for doc in corpus.documents.values()
    ])

    chunk_tags = {entry["chunk"]: entry for entry in corpus.chunk_tags}
    chunk_objects = []
    for key, chunk in chunks.items():
        year = corpus.documents[chunk["document"]]["properties"].get("yearIssued")
        references = {
            "document": corpus.documents[chunk["document"]]["id"],
            names.user_collection_link_name: [collections[c]["id"] for c in chunk["collections"]],
        }
        for ref in ("positiveTag", "negativeTag", "automaticTag"):
            tag_keys = chunk_tags.get(key, {}).get(ref, [])
            if tag_keys:
                references[ref] = [tags[t]["id"] for t in tag_keys]
        chunk_objects.append(DataObject(
            uuid=chunk["id"],
            properties={
                "text": chunk["text"],
                "title": chunk["title"],
                "order": chunk["order"],
                "language": "ces",
                "start_page_id": chunk["start_page_id"],
                "from_page": chunk["from_page"],
                "to_page": chunk["to_page"],
                "end_paragraph": True,
                **({"yearIssued": year} if year is not None else {}),
                **corpus.chunk_classifications.get(key, {}),
            },
            references=references,
            vector={"default": fake_embedding(chunk["text"]), SECOND_VECTOR: second_embedding(chunk["text"])},
        ))
    await _insert(client, names.chunks_collection_name, chunk_objects)

    await seed_annotations(client, names, corpus)


def _span_object(corpus: Corpus, span: dict, *, legacy: bool) -> DataObject:
    tag, chunk = corpus.tags[span["tag"]], corpus.chunks[span["chunk"]]
    properties = {
        "start": span["start"],
        "end": span["end"],
        "type": span["type"],
        **({"reason": span["reason"]} if "reason" in span else {}),
        **({"confidence": span["confidence"]} if "confidence" in span else {}),
    }
    if legacy:
        return DataObject(uuid=span["id"], properties=properties,
                          references={"tag": tag["id"], "text_chunk": chunk["id"]})
    properties |= {"tagId": tag["id"], "chunkId": chunk["id"], "documentId": corpus.documents[chunk["document"]]["id"]}
    return DataObject(uuid=span["id"], properties=properties, references={"text_chunk": chunk["id"]})


async def seed_annotations(client: WeaviateAsyncClient, names: CollectionNames, corpus: Corpus) -> None:
    """The corpus spans in the annotation tenants of their tags' collections (#327)."""
    by_collection: dict[str, list[DataObject]] = {}
    for span in corpus.spans.values():
        collection = corpus.collections[corpus.tags[span["tag"]]["collection"]]["id"]
        by_collection.setdefault(collection, []).append(_span_object(corpus, span, legacy=False))
    annotations = client.collections.get(names.annotation_collection_name)
    await annotations.tenants.create([Tenant(name=str(UUID(c))) for c in by_collection])
    for collection, objects in by_collection.items():
        result = await annotations.with_tenant(str(UUID(collection))).data.insert_many(objects)
        if result.has_errors:
            raise RuntimeError(f"Seeding the annotations of {collection} failed: {result.errors}")


async def seed_legacy_spans(client: WeaviateAsyncClient, names: CollectionNames, corpus: Corpus) -> None:
    """The corpus spans in the legacy single-tenant ``Span`` collection (migration tests)."""
    await _insert(client, names.span_collection_name,
                  [_span_object(corpus, span, legacy=True) for span in corpus.spans.values()])


@cache
def _password_hash(password: str) -> str:
    # Hashing is deliberately slow; integration tests seed the same users for every test.
    return PasswordHelper().hash(password)


async def seed_users(engine: AsyncEngine, corpus: Corpus) -> None:
    """Create the SQL tables and the corpus users (fixed ids and passwords)."""
    await create_tables(engine)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        session.add_all([
            User(
                id=UUID(user["id"]),
                email=user["email"],
                username=user["username"],
                name=user["name"],
                hashed_password=_password_hash(user["password"]),
                is_active=True,
                is_superuser=user["is_superuser"],
                is_verified=True,
            )
            for user in corpus.users.values()
        ])
        await session.commit()
