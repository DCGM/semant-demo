"""The schema command of the chunks' classification status (#590) against the real test store.

A populated chunk collection served through an alias, as in production: the property is added
to the collection behind the alias (Weaviate adds properties only by the collection's name),
once; existing chunks get no value; a property declared differently, or a missing
collection, is refused before anything is added.
"""
from uuid import UUID

import pytest
from weaviate.classes.config import DataType, Property, Tokenization
from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate import classification_provenance as provenance
from semant_demo.adapters.weaviate.chunk_summaries import declared_properties
from semant_demo.maintenance import classification_provenance_schema as schema

pytestmark = pytest.mark.integration

CHUNKS, ALIAS = "ProvenanceChunks", "ProvenanceChunksAlias"
STORED = UUID(int=1)


@pytest.fixture
async def chunks_store(weaviate_client, collection_names):
    client = weaviate_client

    async def drop():
        if await client.alias.get(alias_name=ALIAS):
            await client.alias.delete(alias_name=ALIAS)
        await client.collections.delete(CHUNKS)

    async def create(*properties: Property):
        await client.collections.create(CHUNKS, properties=[Property(name="text", data_type=DataType.TEXT),
                                                            *properties])
        await client.alias.create(alias_name=ALIAS, target_collection=CHUNKS)
        await client.collections.get(CHUNKS).data.insert(uuid=STORED, properties={"text": "stored"})
    await drop()
    try:
        yield client, collection_names.model_copy(update={"chunks_collection_name": ALIAS}), create
    finally:
        await drop()


async def test_the_property_is_added_once_behind_the_alias_and_existing_chunks_get_no_value(chunks_store):
    client, names, create = chunks_store
    await create()

    checked = await schema.update(client, names, apply=False)
    assert checked == {"chunks": CHUNKS, "property": provenance.PROPERTY,
                       "expected": {"data_type": "text", "tokenization": "field", "filterable": True},
                       "missing": True, "added": False}
    assert provenance.PROPERTY not in await declared_properties(client, CHUNKS)

    applied = await schema.update(client, names, apply=True)
    again = await schema.update(client, names, apply=True)
    assert (applied["missing"], applied["added"]) == (False, True)
    assert (again["missing"], again["added"]) == (False, False)
    assert (await declared_properties(client, CHUNKS))[provenance.PROPERTY] == provenance.EXPECTED

    chunks = client.collections.get(ALIAS)
    assert (await chunks.query.fetch_object_by_id(STORED)).properties.get(provenance.PROPERTY) is None
    new = await chunks.data.insert(properties={"text": "new", provenance.PROPERTY: provenance.UNPROCESSED})
    selected = await chunks.query.fetch_objects(
        filters=Filter.by_property(provenance.PROPERTY).equal(provenance.UNPROCESSED), limit=10)
    assert [o.uuid for o in selected.objects] == [new]


async def test_a_property_declared_differently_is_refused(chunks_store):
    client, names, create = chunks_store
    await create(Property(name=provenance.PROPERTY, data_type=DataType.TEXT, tokenization=Tokenization.WORD))
    for apply in (False, True):
        with pytest.raises(schema.Refused, match="separate, reviewed migration"):
            await schema.update(client, names, apply=apply)
    assert (await declared_properties(client, CHUNKS))[provenance.PROPERTY].tokenization == "word"


async def test_a_missing_collection_is_refused(chunks_store):
    client, names, _ = chunks_store
    with pytest.raises(schema.Refused, match="does not exist"):
        await schema.update(client, names, apply=True)
    assert not await client.collections.exists(ALIAS)
