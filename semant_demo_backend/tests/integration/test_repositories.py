"""Weaviate repositories (adapters/weaviate) against the real test store (#202).

Covers missing ids, mapping to application schemas, reads spanning several pages,
cascading deletes over more than a page of matches, and repeated attach/remove.
"""
from uuid import UUID, uuid4

import pytest
from weaviate.classes.data import DataObject
from weaviate.classes.query import QueryReference

from semant_demo.core.errors import NotFoundError
from semant_demo.schema.collections import PatchCollection
from semant_demo.schema.tags import PatchTag, PostTag
from semant_demo.schemas import SpanType
from tests.fakes import fake_embedding
from tests.seed import FIXTURE_TIMESTAMP

pytestmark = pytest.mark.integration

UNKNOWN = UUID("5e3a0000-0000-4000-8000-00000000ffff")
BIG_DOCUMENT_CHUNKS = 205  # more than two pages of 100


def col(corpus, key) -> UUID:
    return UUID(corpus.collections[key]["id"])


def doc(corpus, key) -> UUID:
    return UUID(corpus.documents[key]["id"])


async def insert(client, collection: str, objects: list[DataObject]) -> None:
    result = await client.collections.get(collection).data.insert_many(objects)
    assert not result.has_errors, result.errors


async def ref_list(client, collection: str, uuid, prop: str) -> list[str]:
    """The reference targets of one object, duplicates included."""
    obj = await client.collections.get(collection).query.fetch_object_by_id(
        uuid, return_properties=[], return_references=[QueryReference(link_on=prop)])
    refs = obj.references.get(prop) if obj.references else None
    return [str(r.uuid) for r in (refs.objects if refs else [])]


async def count(client, collection: str) -> int:
    return (await client.collections.get(collection).aggregate.over_all(total_count=True)).total_count


@pytest.fixture
async def big_document(seeded_store, collection_names):
    """A document in no collection with BIG_DOCUMENT_CHUNKS chunks (orders 0..n-1)."""
    names = collection_names
    document_id = uuid4()
    await insert(seeded_store, names.document_collection_name,
                 [DataObject(uuid=document_id, properties={"title": "Velký dokument"})])
    chunk_ids = [uuid4() for _ in range(BIG_DOCUMENT_CHUNKS)]
    await insert(seeded_store, names.chunks_collection_name, [
        DataObject(
            uuid=chunk_id,
            properties={"text": f"Odstavec {i}", "title": "Velký dokument", "order": i, "language": "ces",
                        "start_page_id": str(UUID(int=i + 1)), "from_page": i, "to_page": i,
                        "end_paragraph": True},
            references={"document": str(document_id)},
            vector={"default": fake_embedding(f"Odstavec {i}")},
        )
        for i, chunk_id in enumerate(chunk_ids)
    ])
    return document_id, chunk_ids


#############
# Missing ids #
#############

async def test_reads_of_missing_objects_return_none_or_empty(documents, tags, collections, corpus):
    chronicles = col(corpus, "chronicles")

    assert await documents.read(UNKNOWN) is None
    assert await documents.read_chunks(UNKNOWN, chronicles) is None
    assert await documents.count_chunks(UNKNOWN) == 0
    assert await tags.read(UNKNOWN) is None
    assert await tags.read_collection_ids([UNKNOWN]) == {}
    assert await tags.read_by_collection(UNKNOWN) == []
    assert await collections.read(UNKNOWN) is None
    assert await collections.read_access_record(UNKNOWN) is None
    assert await collections.read_collection_stats(UNKNOWN) is None
    assert await collections.read_all_documents(UNKNOWN) == []
    assert not await collections.document_in_collection(UNKNOWN, chronicles)
    assert await collections.chunk_ids_in_collection([UNKNOWN], chronicles) == set()


OWNER_ID = UUID("5e3a0000-0000-4000-8000-00000000a001")
NEW_TAG = PostTag(name="Nový", shorthand="N", color="red", pictogram="x", definition="d")

MISSING_ID_OPERATIONS = {
    "create tag in unknown collection": lambda t, c, k: t.create(UNKNOWN, NEW_TAG),
    "update unknown tag": lambda t, c, k: t.update(UNKNOWN, PatchTag(name="x")),
    "delete unknown tag": lambda t, c, k: t.delete(UNKNOWN),
    "update unknown collection": lambda t, c, k: c.update(UNKNOWN, PatchCollection(name="x")),
    "set owner of unknown collection": lambda t, c, k: c.set_owner(UNKNOWN, OWNER_ID, "x"),
    "delete unknown collection": lambda t, c, k: c.delete(UNKNOWN),
    "share unknown collection": lambda t, c, k: c.share(UNKNOWN, OWNER_ID),
    "unshare unknown collection": lambda t, c, k: c.unshare(UNKNOWN, OWNER_ID),
    "members of unknown collection": lambda t, c, k: c.read_shared_user_ids(UNKNOWN),
    "add unknown chunk": lambda t, c, k: c.add_chunk(UNKNOWN, k),
    "remove unknown chunk": lambda t, c, k: c.remove_chunk(UNKNOWN, k),
    "add unknown document": lambda t, c, k: c.add_document(UNKNOWN, k),
    "remove unknown document": lambda t, c, k: c.remove_document(UNKNOWN, k),
}


@pytest.mark.parametrize("operation", MISSING_ID_OPERATIONS.values(), ids=MISSING_ID_OPERATIONS.keys())
async def test_operations_on_missing_objects_raise_not_found_and_write_nothing(
        operation, tags, collections, corpus, seeded_store, collection_names):
    names = collection_names
    before = {n: await count(seeded_store, n) for n in (names.tag_collection_name, names.user_collection_name)}

    with pytest.raises(NotFoundError):
        await operation(tags, collections, col(corpus, "newspapers"))

    assert {n: await count(seeded_store, n) for n in before} == before


###########
# Mapping #
###########

async def test_document_maps_stored_properties(documents, corpus):
    chronicle = corpus.documents["chronicle"]

    document = await documents.read(UUID(chronicle["id"]))

    assert str(document.id) == chronicle["id"]
    assert document.model_dump(exclude_none=True, exclude={"id"}) == chronicle["properties"]


@pytest.mark.parametrize("collection", ["newspapers", "outsider_notes", "chronicles"])
async def test_document_chunks_mark_membership_of_the_requested_collection(documents, corpus, collection):
    # The gazette has no authors; documents with authors fail here (#215).
    detail = await documents.read_chunks(doc(corpus, "gazette"), col(corpus, collection))

    assert detail.document.title == corpus.documents["gazette"]["properties"]["title"]
    assert {str(c.id): c.in_user_collection for c in detail.chunks} == {
        corpus.chunks[key]["id"]: collection in corpus.chunks[key]["collections"]
        for key in ("gazette_1", "gazette_2")
    }


async def test_tag_maps_stored_properties(tags, corpus):
    person = corpus.tags["person"]

    tag = await tags.read(UUID(person["id"]))

    assert tag.model_dump(mode="json") == {
        "id": person["id"], "name": person["name"], "shorthand": person["shorthand"], "color": person["color"],
        "pictogram": person["pictogram"], "definition": person["definition"], "examples": person["examples"],
    }
    assert {str(t.id) for t in await tags.read_by_collection(col(corpus, "chronicles"))} == {
        corpus.tags["person"]["id"], corpus.tags["place"]["id"]}
    assert await tags.read_collection_ids([UUID(person["id"])]) == {UUID(person["id"]): [col(corpus, "chronicles")]}


async def test_collection_maps_stored_properties(collections, corpus):
    chronicles = corpus.collections["chronicles"]

    collection = await collections.read(UUID(chronicles["id"]))

    assert (collection.name, collection.description, collection.color, collection.owner) == (
        chronicles["name"], chronicles["description"], chronicles["color"], corpus.users["owner"]["name"])
    assert collection.created_at == collection.updated_at == FIXTURE_TIMESTAMP
    assert await collections.read_access_record(UUID(chronicles["id"])) == (
        UUID(corpus.users["owner"]["id"]), {UUID(corpus.users["annotator"]["id"])})
    assert await collections.read_shared_user_ids(UUID(chronicles["id"])) == [UUID(corpus.users["annotator"]["id"])]


async def test_chunk_maps_stored_properties(collections, corpus):
    expected = corpus.chunks["chronicle_1"]

    [first, _] = await collections.read_all_chunks_by_document(doc(corpus, "chronicle"), col(corpus, "chronicles"))

    assert first.model_dump(mode="json", exclude_none=True) == {
        "id": expected["id"], "text": expected["text"], "order": expected["order"], "title": expected["title"],
        "start_page_id": expected["start_page_id"], "from_page": expected["from_page"],
        "to_page": expected["to_page"], "end_paragraph": True, "in_collection": True,
    }


async def test_neighbour_chunks_and_their_membership(collections, corpus):
    chronicle, chronicles = doc(corpus, "chronicle"), col(corpus, "chronicles")

    after_first = await collections.get_neighbour_chunk(chronicle, chronicles, "next", 0)
    before_last = await collections.get_neighbour_chunk(chronicle, chronicles, "prev", 2)
    after_last = await collections.get_neighbour_chunk(chronicle, chronicles, "next", 1)

    assert (after_first.order, after_first.in_collection) == (1, True)
    assert (before_last.order, before_last.in_collection) == (1, True)
    assert (after_last.order, after_last.in_collection) == (2, False)
    assert await collections.get_neighbour_chunk(chronicle, chronicles, "next", 2) is None


async def test_browse_scopes_filters_and_pages(documents, corpus):
    in_newspapers = await documents.browse(collection_id=col(corpus, "newspapers"), limit=1, sort_by="title")
    by_title = await documents.browse(title="Kronika")

    assert in_newspapers.total_count == 2 and in_newspapers.has_more and in_newspapers.next_offset == 1
    assert len(in_newspapers.items) == 1
    assert [str(d.id) for d in by_title.items] == [corpus.documents["chronicle"]["id"]]
    assert not by_title.has_more and by_title.next_offset is None


##############
# Many pages #
##############

async def test_document_reads_span_several_pages(documents, collections, big_document, corpus):
    document_id, chunk_ids = big_document
    chronicles = col(corpus, "chronicles")

    detail = await documents.read_chunks(document_id, chronicles)
    all_chunks = await collections.get_chunks_in_range(document_id, chronicles, None, None)
    middle = await collections.get_chunks_in_range(document_id, chronicles, 99, 201)

    assert await documents.count_chunks(document_id) == BIG_DOCUMENT_CHUNKS
    assert sorted(c.id for c in detail.chunks) == sorted(chunk_ids)
    assert [c.order for c in all_chunks] == list(range(BIG_DOCUMENT_CHUNKS))
    assert [c.order for c in middle] == list(range(100, 201))


async def test_add_and_remove_a_document_with_several_pages_of_chunks(collections, big_document, corpus,
                                                                      seeded_store, collection_names):
    document_id, chunk_ids = big_document
    newspapers = col(corpus, "newspapers")

    added = await collections.add_document(document_id, newspapers)

    assert added.outcome == "complete" and len(added.succeeded) == BIG_DOCUMENT_CHUNKS + 1
    members = await collections.read_all_chunks_by_document(document_id, newspapers)
    assert [c.order for c in members] == list(range(BIG_DOCUMENT_CHUNKS))
    stats = await collections.read_document_stats(newspapers, document_id)
    assert (stats.chunks_in_collection, stats.total_chunks) == (BIG_DOCUMENT_CHUNKS, BIG_DOCUMENT_CHUNKS)

    # Unlinking removes chunks from the listing filter while the operation runs.
    removed = await collections.remove_document(document_id, newspapers)

    assert removed.outcome == "complete" and len(removed.succeeded) == BIG_DOCUMENT_CHUNKS + 1
    assert await collections.read_all_chunks_by_document(document_id, newspapers) == []
    assert not await collections.document_in_collection(document_id, newspapers)
    assert await ref_list(seeded_store, collection_names.chunks_collection_name, chunk_ids[-1],
                          collection_names.user_collection_link_name) == []


async def test_collection_documents_beyond_the_default_query_limit(collections, corpus, seeded_store,
                                                                   collection_names):
    chronicles = col(corpus, "chronicles")
    extra = [uuid4() for _ in range(30)]
    await insert(seeded_store, collection_names.document_collection_name, [
        DataObject(uuid=d, properties={"title": f"Dopis {i}"}, references={"collection": str(chronicles)})
        for i, d in enumerate(extra)
    ])

    listed = {d.id for d in await collections.read_all_documents(chronicles)}

    assert listed == set(extra) | {doc(corpus, "chronicle"), doc(corpus, "letters")}


async def test_collection_tags_beyond_one_page(tags, corpus, seeded_store, collection_names):
    chronicles = col(corpus, "chronicles")
    extra = [uuid4() for _ in range(105)]
    await insert(seeded_store, collection_names.tag_collection_name, [
        DataObject(uuid=t, properties={"tag_name": f"Štítek {i}", "tag_shorthand": "Š", "tag_color": "red",
                                       "tag_pictogram": "x", "tag_definition": "d", "tag_examples": []},
                   references={"userCollection": str(chronicles)})
        for i, t in enumerate(extra)
    ])

    listed = {t.id for t in await tags.read_by_collection(chronicles)}

    assert listed == set(extra) | {UUID(corpus.tags["person"]["id"]), UUID(corpus.tags["place"]["id"])}


async def test_tag_delete_removes_more_than_a_page_of_references_and_spans(
        tags, big_document, corpus, seeded_store, collection_names):
    names = collection_names
    _, chunk_ids = big_document
    place = UUID(corpus.tags["place"]["id"])
    tagged = chunk_ids[:150]
    chunks = seeded_store.collections.get(names.chunks_collection_name)
    for chunk_id in tagged:
        await chunks.data.reference_add(from_uuid=chunk_id, from_property="positiveTag", to=place)
    await insert(seeded_store, names.span_collection_name, [
        DataObject(properties={"start": 0, "end": 8, "type": SpanType.pos},
                   references={"tag": str(place), "text_chunk": str(chunk_id)})
        for chunk_id in tagged
    ])
    spans_before = await count(seeded_store, names.span_collection_name)

    await tags.delete(place)

    assert await tags.read(place) is None
    place_corpus_spans = sum(1 for s in corpus.spans.values() if s["tag"] == "place")
    assert await count(seeded_store, names.span_collection_name) == spans_before - 150 - place_corpus_spans
    assert all([await ref_list(seeded_store, names.chunks_collection_name, c, "positiveTag") == []
                for c in (tagged[0], tagged[99], tagged[100], tagged[-1])])
    assert await ref_list(seeded_store, names.chunks_collection_name, corpus.chunks["chronicle_1"]["id"],
                          "automaticTag") == []
    # Other tags keep their references.
    person_chunk = corpus.chunks["chronicle_1"]["id"]
    assert corpus.tags["person"]["id"] in await ref_list(seeded_store, names.chunks_collection_name,
                                                         person_chunk, "positiveTag")


async def test_collection_delete_unlinks_more_than_a_page_of_chunks(
        collections, tags, big_document, corpus, seeded_store, collection_names):
    names = collection_names
    document_id, chunk_ids = big_document
    newspapers = col(corpus, "newspapers")
    await collections.add_document(document_id, newspapers)

    await collections.delete(newspapers)

    assert await collections.read(newspapers) is None
    assert await tags.read(UUID(corpus.tags["event"]["id"])) is None
    for chunk_id in (chunk_ids[0], chunk_ids[150], chunk_ids[-1]):
        assert await ref_list(seeded_store, names.chunks_collection_name, chunk_id, names.user_collection_link_name) == []
    assert str(newspapers) not in await ref_list(seeded_store, names.document_collection_name,
                                                 doc(corpus, "chronicle"), "collection")
    # Other collections keep their members.
    assert await collections.document_in_collection(doc(corpus, "chronicle"), col(corpus, "chronicles"))
    assert await collections.document_in_collection(doc(corpus, "gazette"), col(corpus, "outsider_notes"))


#########################
# Repeated attach/remove #
#########################

async def test_adding_a_chunk_twice_links_it_once(collections, corpus, seeded_store, collection_names):
    names = collection_names
    chunk = UUID(corpus.chunks["letters_1"]["id"])
    newspapers = col(corpus, "newspapers")

    first = await collections.add_chunk(chunk, newspapers)
    second = await collections.add_chunk(chunk, newspapers)

    assert first.outcome == second.outcome == "complete"
    assert first.succeeded == second.succeeded == [str(chunk), str(doc(corpus, "letters"))]
    assert (await ref_list(seeded_store, names.chunks_collection_name, chunk, names.user_collection_link_name)
            ).count(str(newspapers)) == 1
    assert (await ref_list(seeded_store, names.document_collection_name, doc(corpus, "letters"), "collection")
            ).count(str(newspapers)) == 1


async def test_removing_a_chunk_twice_is_a_no_op_the_second_time(collections, corpus):
    chunk = UUID(corpus.chunks["chronicle_1"]["id"])
    chronicles = col(corpus, "chronicles")

    await collections.remove_chunk(chunk, chronicles)
    await collections.remove_chunk(chunk, chronicles)

    assert await collections.chunk_ids_in_collection([chunk], chronicles) == set()
    # Removing a chunk does not unlink its document.
    assert await collections.document_in_collection(doc(corpus, "chronicle"), chronicles)


async def test_adding_and_removing_a_document_twice(collections, corpus, seeded_store, collection_names):
    names = collection_names
    gazette, chronicles = doc(corpus, "gazette"), col(corpus, "chronicles")
    gazette_chunks = [corpus.chunks["gazette_1"]["id"], corpus.chunks["gazette_2"]["id"]]

    added = [await collections.add_document(gazette, chronicles) for _ in range(2)]

    assert [r.outcome for r in added] == ["complete", "complete"]
    assert (await ref_list(seeded_store, names.document_collection_name, gazette, "collection")
            ).count(str(chronicles)) == 1
    for chunk in gazette_chunks:
        assert (await ref_list(seeded_store, names.chunks_collection_name, chunk, names.user_collection_link_name)
                ).count(str(chronicles)) == 1

    removed = [await collections.remove_document(gazette, chronicles) for _ in range(2)]

    assert [r.outcome for r in removed] == ["complete", "complete"]
    assert set(removed[0].succeeded) == set(gazette_chunks) | {str(gazette)}
    assert removed[1].succeeded == [str(gazette)] and removed[1].failed == []
    assert not await collections.document_in_collection(gazette, chronicles)
    # Its other collections are untouched.
    assert await collections.document_in_collection(gazette, col(corpus, "outsider_notes"))


async def test_sharing_and_unsharing_twice(collections, corpus):
    newspapers, annotator = col(corpus, "newspapers"), UUID(corpus.users["annotator"]["id"])

    for _ in range(2):
        await collections.share(newspapers, annotator)
    assert await collections.read_shared_user_ids(newspapers) == [annotator]

    for _ in range(2):
        await collections.unshare(newspapers, annotator)
    assert await collections.read_shared_user_ids(newspapers) == []
