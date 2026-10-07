"""Write the fixture corpus into a test-owned Weaviate store and a test SQL database."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi_users.password import PasswordHelper
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from weaviate import WeaviateAsyncClient
from weaviate.classes.data import DataObject

from semant_demo.schemas import CollectionNames, TasksBase
from semant_demo.users.models import User
from tests.corpus import Corpus
from tests.fakes import fake_embedding
from tests.weaviate_store import claim_store

FIXTURE_TIMESTAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _insert(client: WeaviateAsyncClient, collection: str, objects: list[DataObject]) -> None:
    result = await client.collections.get(collection).data.insert_many(objects)
    if result.has_errors:
        raise RuntimeError(f"Seeding {collection} failed: {result.errors}")


async def seed_weaviate(client: WeaviateAsyncClient, names: CollectionNames, corpus: Corpus, token: str) -> None:
    """Insert the corpus into the (already created, empty) application collections."""
    await claim_store(client, token)
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
            },
            references=references,
            vector={"default": fake_embedding(chunk["text"])},
        ))
    await _insert(client, names.chunks_collection_name, chunk_objects)

    await _insert(client, names.span_collection_name, [
        DataObject(
            uuid=span["id"],
            properties={
                "start": span["start"],
                "end": span["end"],
                "type": span["type"],
                **({"reason": span["reason"]} if "reason" in span else {}),
                **({"confidence": span["confidence"]} if "confidence" in span else {}),
            },
            references={"tag": tags[span["tag"]]["id"], "text_chunk": chunks[span["chunk"]]["id"]},
        )
        for span in corpus.spans.values()
    ])


async def seed_users(engine: AsyncEngine, corpus: Corpus) -> None:
    """Create the SQL tables and the corpus users (fixed ids and passwords)."""
    async with engine.begin() as conn:
        await conn.run_sync(TasksBase.metadata.create_all)
    password_helper = PasswordHelper()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        session.add_all([
            User(
                id=UUID(user["id"]),
                email=user["email"],
                username=user["username"],
                name=user["name"],
                hashed_password=password_helper.hash(user["password"]),
                is_active=True,
                is_superuser=user["is_superuser"],
                is_verified=True,
            )
            for user in corpus.users.values()
        ])
        await session.commit()
