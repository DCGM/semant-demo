"""Chunk retrieval: neutral ``ChunkQuery`` -> Weaviate BM25/near-vector/hybrid query -> chunks.

Owns filter translation, the choice of query call, the returned references/properties and
the mapping of result objects. Embeddings are computed by the caller (``query.vector``);
no provider is called here.
"""
from collections.abc import Mapping
from typing import Any

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import Metrics
from weaviate.classes.query import Filter, QueryReference

import semant_demo.schemas as schemas
from semant_demo.adapters.weaviate.chunk_tags import REF_BY_TYPE
from semant_demo.features.annotations.schemas import SpanType
from semant_demo.features.search.filters import TASK_CLASSES
from semant_demo.features.search.schemas import ChunkQuery, FieldCondition, Op, SearchType, TagFilter, TextChunkWithDocument
from semant_demo.schema.documents import Document

# Fields stored on the chunk's document, not on the chunk; filtered through the reference.
DOCUMENT_FIELDS = {
    "yearIssued", "dateIssued", "documentType", "publisher", "placeTerm",
    "genre", "public", "url", "library", "title", "subTitle", "partNumber",
    "partName", "authors", "description", "keywords", "section", "region", "id_code"
}

# Document properties returned with each hit: every field of the document model. A store
# without some of them returns the others.
DOCUMENT_PROPERTIES = [name for name in Document.model_fields if name != "id"]

# Chunk tag references: the projection of the spans (ADR 0004, chunk_tags.py).
AUTOMATIC_TAG_REF = REF_BY_TYPE[SpanType.auto.value]
POSITIVE_TAG_REF = REF_BY_TYPE[SpanType.pos.value]


class ChunkSearchRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

    async def search(self, query: ChunkQuery) -> list[TextChunkWithDocument]:
        """Top ``query.limit`` chunks matching every condition, best first.

        Chunks without a document reference are left out.
        """
        chunks = self.client.collections.get(self.collectionNames.chunks_collection_name)
        common = dict(
            limit=query.limit,
            filters=self._filter(query),
            return_references=[QueryReference(link_on="document", return_properties=DOCUMENT_PROPERTIES)],
        )
        if query.mode == SearchType.text:
            result = await chunks.query.bm25(query=query.text, **common)
        elif query.mode == SearchType.vector:
            result = await chunks.query.near_vector(near_vector=_vector(query), **common)
        elif query.mode == SearchType.hybrid:
            result = await chunks.query.hybrid(query=query.text, alpha=query.alpha, vector=_vector(query), **common)
        else:
            raise ValueError(f"Unknown search type: {query.mode}")

        results: list[TextChunkWithDocument] = []
        for obj in result.objects:
            doc_objs = obj.references.get("document").objects if obj.references and obj.references.get("document") else []
            if not doc_objs:
                continue
            first_doc = doc_objs[0]
            doc_props = dict(first_doc.properties)
            if not doc_props.get("library"):
                doc_props["library"] = "mzk"
            results.append(TextChunkWithDocument(
                id=obj.uuid,
                **obj.properties,
                document_object=Document(id=first_doc.uuid, **doc_props),
                document=first_doc.uuid,
                metadata=classifications(obj.properties),
            ))
        return results

    async def document_filter_stats(self) -> tuple[int | None, int | None, list[str] | None]:
        """(min yearIssued, max yearIssued, languages) over all documents; None where unknown."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        min_year = max_year = None
        res_year = await documents.aggregate.over_all(
            return_metrics=[Metrics("yearIssued").integer(minimum=True, maximum=True)]
        )
        if "yearIssued" in res_year.properties:
            if res_year.properties["yearIssued"].minimum is not None:
                min_year = int(res_year.properties["yearIssued"].minimum)
            if res_year.properties["yearIssued"].maximum is not None:
                max_year = int(res_year.properties["yearIssued"].maximum)

        res_lang = await documents.aggregate.over_all(
            return_metrics=[Metrics("language").text(top_occurrences_value=True, limit=1000)]
        )
        languages = []
        if "language" in res_lang.properties and res_lang.properties["language"].top_occurrences:
            languages = [top.value for top in res_lang.properties["language"].top_occurrences if top.value]
        return min_year, max_year, languages or None

    def _filter(self, query: ChunkQuery):
        filters = []
        if query.collection_id is not None:
            filters.append(Filter.by_ref(link_on=self.collectionNames.user_collection_link_name)
                           .by_id().equal(query.collection_id))
        filters.extend(_condition(c) for c in query.conditions)
        if query.tags is not None:
            filters.append(_tag_filter(query.tags))
        if not filters:
            return None
        return Filter.all_of(filters) if len(filters) > 1 else filters[0]


def classifications(properties: Mapping[str, Any]) -> dict[str, list[str]]:
    """The populated classification properties (``TASK_CLASSES``) of a chunk, in that order.

    Stored as ``text[]``; a single value (older data, e.g. a string) becomes a one-element
    list of its text. Empty and repeated values are dropped, other properties are never
    included.
    """
    result = {}
    for name in TASK_CLASSES:
        stored = properties.get(name)
        if stored is None:
            continue
        values = stored if isinstance(stored, (list, tuple)) else [stored]
        values = list(dict.fromkeys(str(v) for v in values if v is not None and v != ""))
        if values:
            result[name] = values
    return result


def _vector(query: ChunkQuery) -> list[float]:
    if query.vector is None:
        raise ValueError(f"{query.mode.value} search needs a query vector")
    return query.vector


def _condition(condition: FieldCondition):
    if condition.field in DOCUMENT_FIELDS:
        target = Filter.by_ref(link_on="document").by_property(condition.field)
    else:
        target = Filter.by_property(condition.field)
    if condition.op == Op.equal:
        return target.equal(condition.value)
    if condition.op == Op.greater_or_equal:
        return target.greater_or_equal(condition.value)
    if condition.op == Op.less_or_equal:
        return target.less_or_equal(condition.value)
    if condition.op == Op.contains_any:
        return target.contains_any(list(condition.value))
    raise ValueError(f"Unsupported filter operation: {condition.op}")


def _tag_filter(tags: TagFilter):
    ids = list(tags.tag_ids)
    kinds = []
    if tags.automatic:
        kinds.append(Filter.by_ref(AUTOMATIC_TAG_REF).by_id().contains_any(ids))
    if tags.positive:
        kinds.append(Filter.by_ref(POSITIVE_TAG_REF).by_id().contains_any(ids))
    if not kinds:
        raise ValueError("A tag filter needs at least one tag kind")
    return Filter.any_of(kinds) if len(kinds) > 1 else kinds[0]
