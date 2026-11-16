"""Czech text and context sorts and the attribute sort against real Weaviate (#666).

Weaviate sorts the stored hex collation keys by code point; the order must be Czech
dictionary order of the words, in both directions, with ties by id and pages that together
are exactly one full read. Rows without a key (no word on that side, not derived, or not yet
backfilled) take Weaviate's own placement of missing values, observed here: first ascending,
last descending. The attribute sort's partition filters, and ``add-schema`` with the sort key
backfill on a collection created before #666.
"""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty, Tokenization

from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.spans import (
    ATTRIBUTE_PROPERTIES, ENRICHMENT_PROPERTIES, SORT_KEY_PROPERTIES, SpanRepository, add_enrichment_schema,
    sort_key_schema,
)
from semant_demo.bootstrap import detect_enrichment
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations import backfill, service
from semant_demo.features.annotations.collation import NO_SORT_KEYS, sort_key_version, sort_keys
from semant_demo.features.annotations.derivation import DERIVATION_VERSION
from semant_demo.features.annotations.enrichment import Enrichment
from semant_demo.features.annotations.schemas import AnnotationFilters, AnnotationSort, PostSpan, SpanType
from semant_demo.features.annotations.service import AnnotationStore

pytestmark = pytest.mark.integration


@pytest.fixture
def store(seeded_store, collection_names, documents) -> AnnotationStore:
    """With the sort keys and attributes the seeded schema holds."""
    spans = SpanRepository(seeded_store, collection_names, attributes=True, sort_keys=True)
    return AnnotationStore(collections=UserCollectionRepository(seeded_store, collection_names, spans),
                           tags=TagRepository(seeded_store, collection_names, spans), spans=spans,
                           chunk_tags=ChunkTagRepository(seeded_store, collection_names, spans),
                           documents=documents, enrichment=Enrichment(derived=True, sort_keys=True))


@pytest.fixture
def owner(ids):
    return SimpleNamespace(id=UUID(ids.user["owner"]), is_superuser=False)


def derived(text: str, left: str, right: str, start: int, keys: bool = True) -> dict:
    """Derived properties of a span with this text and context, current, with or without keys."""
    props = {"revision": 1, "enrichedRevision": 1, "enrichmentStatus": "ready", "derivationVersion": DERIVATION_VERSION,
             "text": text, "leftContext": left, "rightContext": right, "documentStartChar": start,
             "documentEndChar": start + len(text), "documentStartWord": start, "documentEndWord": start + 1}
    return props | (sort_keys(text, left, right).properties(1) if keys else {})


async def insert(store, ids, document: str, chunk: str, derived_props: dict | None, values=(), type="pos") -> UUID:
    span = PostSpan(chunkId=ids.chunk[chunk], tagId=ids.tag["person"], start=0, end=1, type=SpanType(type))
    sid = await store.spans.insert(UUID(ids.col["chronicles"]), span, UUID(ids.doc[document]), derived_props)
    if values:
        await store.spans.write_attributes(UUID(ids.col["chronicles"]), sid, list(values), 1)
    return sid


async def read(store, owner, ids, within, size, **kwargs) -> tuple[list[UUID], int, int | None]:
    """Every row of ``within`` by pages of ``size``, the total and ``unsortable`` of the first page."""
    rows, offset, unsortable = [], 0, None
    while True:
        page = await service.query_annotations(store, owner, ids.col["chronicles"], AnnotationFilters(),
                                               annotation_ids=within, limit=size, offset=offset, **kwargs)
        rows += [r.id for r in page.rows]
        unsortable = page.unsortable if offset == 0 else unsortable
        offset += size
        if offset >= page.total:
            return rows, page.total, unsortable


WORDS = ["chata", "cesta", "Hrad", "hrad", "hrát", "čas", "dub", "Ch"]
CZECH = ["cesta", "čas", "dub", "dub", "dub", "hrad", "Hrad", "hrát", "Ch", "chata"]
"""``WORDS`` and two more ``dub`` in Czech order (``ch`` after ``h``, case and accents last)."""


@pytest.mark.parametrize("sort", [AnnotationSort.text, AnnotationSort.left, AnnotationSort.right])
async def test_text_and_context_sorts_are_czech_dictionary_order_with_missing_keys_placed_by_weaviate(
        store, owner, ids, sort):
    word_of = {}
    for i, word in enumerate([*WORDS, "dub", "dub"]):
        document, chunk = ("letters", "letters_2") if i % 2 else ("chronicle", "chronicle_1")
        word_of[await insert(store, ids, document, chunk, derived(word, f"slovo {word}", f" {word}, slovo", i))] = word
    empty = await insert(store, ids, "chronicle", "chronicle_1", derived("—", "", ".", 60))  # no word on any side
    unkeyed = await insert(store, ids, "chronicle", "chronicle_1", derived("ano", "ano ", " ano", 61, keys=False))
    pending = await insert(store, ids, "chronicle", "chronicle_1", None)  # never derived
    within = [*word_of, empty, unkeyed, pending]
    dubs = sorted((i for i, w in word_of.items() if w == "dub"), key=str)  # equal keys: by id

    rows, total, unsortable = await read(store, owner, ids, within, 100, sort=sort)
    assert (total, unsortable) == (13, 2)  # the empty key is a current key; unkeyed and pending have none
    # Observed on Weaviate 1.40: rows without a key (missing property or "") first ascending...
    assert set(rows[:3]) == {empty, unkeyed, pending}
    assert [word_of[i] for i in rows[3:]] == CZECH
    assert [i for i in rows if i in dubs] == dubs
    descending, _, _ = await read(store, owner, ids, within, 100, sort=sort, descending=True)
    # ...and last descending; ties stay by id ascending.
    assert set(descending[-3:]) == {empty, unkeyed, pending}
    assert [word_of[i] for i in descending[:-3]] == CZECH[::-1]
    assert [i for i in descending if i in dubs] == dubs
    for size in (1, 2, 5):
        assert (await read(store, owner, ids, within, size, sort=sort))[0] == rows, size
        assert (await read(store, owner, ids, within, size, sort=sort, descending=True))[0] == descending, size


async def test_nearest_left_word_decides_before_the_words_further_away(store, owner, ids):
    near_a = await insert(store, ids, "chronicle", "chronicle_1", derived("X", "zebra žába a ", "", 0))
    near_b = await insert(store, ids, "chronicle", "chronicle_1", derived("X", "ahoj b ", "", 1))
    then_second = await insert(store, ids, "chronicle", "chronicle_1", derived("X", "cizí a ", "", 2))
    rows, _, _ = await read(store, owner, ids, [near_a, near_b, then_second], 10, sort=AnnotationSort.left)
    assert rows == [then_second, near_a, near_b]


class Attributes:
    def __init__(self, attribute, values, retired=()):
        self.attribute = SimpleNamespace(id=attribute, values=[SimpleNamespace(id=v, retired=v in retired)
                                                               for v in values])

    async def read(self, collection_id, attribute_id):
        return self.attribute if attribute_id == self.attribute.id else None


async def test_attribute_sort_partitions_by_first_value_with_missing_and_unapproved_last(store, owner, ids):
    attribute, red, green, old = uuid4(), uuid4(), uuid4(), uuid4()
    definitions = Attributes(attribute, [red, old, green], retired={old})
    e = lambda v: codec.encode(attribute, v)  # noqa: E731
    both = await insert(store, ids, "chronicle", "chronicle_1", derived("a", "", "", 9), [e(green), e(red)])
    red_letter = await insert(store, ids, "letters", "letters_2", derived("b", "", "", 0), [e(red)])
    green_1 = await insert(store, ids, "chronicle", "chronicle_1", derived("c", "", "", 1), [e(green)])
    retired = await insert(store, ids, "chronicle", "chronicle_1", derived("d", "", "", 2), [e(old)])
    rejected = await insert(store, ids, "chronicle", "chronicle_1", derived("e", "", "", 3), [e(red)], type="neg")
    other = await insert(store, ids, "chronicle", "chronicle_1", derived("f", "", "", 4),
                         [codec.encode(uuid4(), uuid4())])
    none = await insert(store, ids, "chronicle", "chronicle_1", derived("g", "", "", 5))
    within = [both, red_letter, green_1, retired, rejected, other, none]
    # Document order within a value: "Dopisy z Prahy" (letters) before "Kronika obce Lhota".
    reds = [red_letter, both]

    rows, total, unsortable = await read(store, owner, ids, within, 100, sort=AnnotationSort.attribute,
                                         sort_attribute=attribute, attributes=definitions)
    assert rows == [*reds, green_1, retired, other, none] and (total, unsortable) == (6, None)
    # Not approved (here rejected, asked for explicitly) annotations show no value: with the missing ones.
    page = await service.query_annotations(
        store, owner, ids.col["chronicles"], AnnotationFilters(types=[SpanType.pos, SpanType.neg]),
        annotation_ids=within, sort=AnnotationSort.attribute, sort_attribute=attribute, attributes=definitions)
    assert [r.id for r in page.rows] == [*reds, green_1, retired, rejected, other, none]
    for size in (1, 2, 4):
        assert (await read(store, owner, ids, within, size, sort=AnnotationSort.attribute,
                           sort_attribute=attribute, attributes=definitions))[0] == rows, size
    descending, _, _ = await read(store, owner, ids, within, 3, sort=AnnotationSort.attribute,
                                  sort_attribute=attribute, attributes=definitions, descending=True)
    # Descending: green, then red (the annotation holding both now sorts under green), retired, missing.
    assert descending == [green_1, both, red_letter, retired, other, none]


async def _create_pre_666_collection(client, names, chunks_collection):
    await client.collections.create(
        names.annotation_collection_name,
        multi_tenancy_config=Configure.multi_tenancy(enabled=True, auto_tenant_creation=False,
                                                     auto_tenant_activation=True),
        vector_config=Configure.Vectors.self_provided(name="default", vector_index_config=Configure.VectorIndex.flat()),
        properties=[
            Property(name="tagId", data_type=DataType.UUID), Property(name="chunkId", data_type=DataType.UUID),
            Property(name="documentId", data_type=DataType.UUID), Property(name="start", data_type=DataType.INT),
            Property(name="end", data_type=DataType.INT),
            Property(name="type", data_type=DataType.TEXT, tokenization=Tokenization.FIELD, index_searchable=False),
            *ENRICHMENT_PROPERTIES, *ATTRIBUTE_PROPERTIES,
        ],
        references=[ReferenceProperty(name="text_chunk", target_collection=chunks_collection)])


async def test_add_schema_adds_the_sort_keys_and_the_backfill_fills_them_without_rederiving(
        seeded_store, collection_names, ids, documents):
    names = collection_names.model_copy(update={"annotation_collection_name": "AnnotationPre666"})
    await _create_pre_666_collection(seeded_store, names, collection_names.chunks_collection_name)
    try:
        spans = SpanRepository(seeded_store, names)
        store = AnnotationStore(collections=None, tags=None, spans=spans, chunk_tags=None, documents=documents)
        collection = UUID(ids.col["chronicles"])
        enrichment = await detect_enrichment(seeded_store, SimpleNamespace(collectionNames=names), None)
        assert enrichment == Enrichment(derived=True, sort_keys=False)
        sid = await spans.insert(collection, PostSpan(chunkId=ids.chunk["chronicle_1"], tagId=ids.tag["person"],
                                                      start=34, end=43, type=SpanType.pos),
                                 UUID(ids.doc["chronicle"]), derived("Jan Novák", "hejtman ", " a", 34, keys=False))

        assert await sort_key_schema(seeded_store, names) == [p.name for p in SORT_KEY_PROPERTIES]
        assert await add_enrichment_schema(seeded_store, names, None) == [p.name for p in SORT_KEY_PROPERTIES]
        assert await add_enrichment_schema(seeded_store, names, None) == []  # idempotent
        store.enrichment = await detect_enrichment(seeded_store, SimpleNamespace(collectionNames=names), None)
        assert store.enrichment.sort_keys
        spans.sort_keys = True

        [report] = await backfill.status(store, [collection])
        assert (report.sort_keys, report.incomplete) == ({"missing": 1}, 1)
        result = await backfill.backfill(store, [collection], limit=10)
        assert (result.sort_keys_written, result.text_written, result.failed) == (1, 0, [])
        row = await spans.read_row(collection, sid)
        assert row.sortKeyVersion == sort_key_version() and row.text == "Jan Novák"

        # Keys of another collator are recomputed; empty keys of a span without text are not.
        await spans.write_derived(collection, sid, {"sortKeyVersion": "0:icu-1.0:00000000"})
        await spans.insert(collection, PostSpan(chunkId=ids.chunk["chronicle_1"], tagId=ids.tag["person"], start=0,
                                                end=1, type=SpanType.pos), UUID(ids.doc["chronicle"]),
                           {"revision": 1, "enrichedRevision": 1, "enrichmentStatus": "invalid",
                            "derivationVersion": DERIVATION_VERSION, "text": "", **NO_SORT_KEYS})
        result = await backfill.backfill(store, [collection], limit=10)
        assert (result.sort_keys_written, result.remaining_incomplete) == (1, 0)
        [report] = await backfill.status(store, [collection])
        assert report.sort_keys == {"current": 1, "pending": 1}
    finally:
        await seeded_store.collections.delete(names.annotation_collection_name)
