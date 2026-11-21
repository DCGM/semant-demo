"""Facet counts of an annotation query (#667): how many annotations each choice of a filter would give.

One definition of the query (``AnnotationFilters``, #663; ``AnnotationRanking``, #664) selects the
population. Lexical queries are counted over every annotation they match, each facet with the
query's filter on that same facet removed (self-exclusion, as faceted search does), so the other
choices of an active filter stay visible; with ``self_exclusion`` false every facet counts the query's
own population instead (the statistics of a query, #818). Ranked queries are counted over exactly the
returned top ``k`` annotations, as they are (re-ranking per facet would change which annotations are
counted).

Counting uses Weaviate aggregations only (no rows are read): ``group_by`` for the single-valued
``tagId`` and ``type``, the per-document counts of ``service._annotated_documents`` plus one read of
those documents for document, year, library and language, and one filtered count per value for an
attribute (``attributeValues`` is an array: per-value counts are exact for multi-valued attributes
without relying on array grouping).
"""
import asyncio
from dataclasses import dataclass
from uuid import UUID

from semant_demo.core.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations import service
from semant_demo.features.annotations.schemas import (
    MAX_FACET_VALUES, AnnotationFacets, AnnotationFacetsRequest, AnnotationFilters, AnnotationQuery, AnnotationSort,
    Facet, FacetPopulation, FacetValue, SpanType,
)
from semant_demo.features.documents.criteria import document_conditions
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal

_MAX_GROUPS = 1000
"""Values of a tag or type aggregation read at most."""


@dataclass
class _Scope:
    """The annotations one facet counts: ``query`` within ``document_ids`` (None: any document)."""
    query: AnnotationQuery
    document_ids: list[UUID] | None
    total: int
    found: "service._Documents | None" = None
    """The annotated documents with their counts, when document filters had to read them."""


def _without(request: AnnotationFacetsRequest, facet: str) -> AnnotationFilters:
    """The query's filters with the filter on ``facet`` itself removed (self-exclusion)."""
    name, _, attribute = facet.partition(":")
    documents = request.document_filters
    if name == "tag":
        update: dict = {"tag_ids": None}
    elif name == "type":
        update = {"types": list(SpanType)}
    elif name == "document":
        update = {"document_ids": None}
    elif name == "year":
        update = {"document_filters": documents.model_copy(update={"year_min": None, "year_max": None})}
    elif name == "library":
        update = {"document_filters": documents.model_copy(update={"libraries": []})}
    elif name == "language":
        update = {"document_filters": documents.model_copy(update={"languages": []})}
    else:
        attribute_id = UUID(attribute)
        update = {"attribute_values": [v for v in request.attribute_values if not v.startswith(f"{attribute_id}:")],
                  "attribute_unassigned": [a for a in request.attribute_unassigned if UUID(str(a)) != attribute_id]}
    return request.model_copy(update=update)


async def _lexical_scope(store: service.AnnotationStore, cid: UUID, filters: AnnotationFilters) -> _Scope:
    query = service._filters_query(filters)
    documents = filters.document_ids or None
    conditions = document_conditions(filters.document_filters)
    # The proximity filter (#333) restricts the annotations before any counting, as for the list.
    query, _ = await service._apply_near(store, cid, filters, query, conditions)
    if conditions:
        found = await service._annotated_documents(store, cid, query, AnnotationSort.document, documents, conditions)
        return _Scope(query, found.order, sum(found.counts.values()), found)
    return _Scope(query, documents, await store.spans.count_rows(cid, query, documents))


def _sorted(counts: dict[str, int]) -> list[FacetValue]:
    return [FacetValue(value=v, count=n) for v, n in sorted(counts.items(), key=lambda c: (-c[1], c[0])) if n]


async def _by_property(store: service.AnnotationStore, cid: UUID, name: str, scope: _Scope) -> Facet:
    prop = {"tag": "tagId", "type": "type"}[name]
    counts = await store.spans.count_by_property(cid, scope.query, prop, _MAX_GROUPS, scope.document_ids)
    return Facet(facet=name, values=_sorted(counts), missing=max(0, scope.total - sum(counts.values())),
                 total=scope.total)


async def _by_document(store: service.AnnotationStore, cid: UUID, name: str, scope: _Scope) -> Facet:
    """Document, year, library and language: the matching annotations per document, then the
    documents' metadata (read once; at most ``service._MAX_DOCUMENTS`` documents, as the filters)."""
    found = scope.found or await service._annotated_documents(
        store, cid, scope.query, AnnotationSort.document, scope.document_ids, [])
    if name == "document":
        values = _sorted({str(d): n for d, n in found.counts.items()})
        return Facet(facet=name, values=values[:MAX_FACET_VALUES], missing=max(0, scope.total - sum(found.counts.values())),
                     total=scope.total, distinct=len(found.counts), truncated=len(values) > MAX_FACET_VALUES)
    counts: dict[str, int] = {}
    for document, n in found.counts.items():
        metadata = found.documents.get(document)
        value = getattr(metadata, {"year": "yearIssued", "library": "library", "language": "language"}[name], None) \
            if metadata is not None else None
        if value is not None and value != "":
            counts[str(value)] = counts.get(str(value), 0) + n
    return Facet(facet=name, values=_sorted(counts), missing=max(0, scope.total - sum(counts.values())),
                 total=scope.total)


async def _by_attribute(store: service.AnnotationStore, cid: UUID, facet: str, scope: _Scope, attribute,
                        limiter: asyncio.Semaphore, statistics: bool = False) -> Facet:
    """Approved annotations holding each value of the attribute (as the attribute filter matches), and
    of them those whose current tag the attribute no longer applies to (#500). An annotation holding
    several values counts once under each.

    ``statistics`` (#819) adds the applicable-only population the accepted-value statistics count:
    ``eligible`` (approved annotations of a tag the attribute applies to), ``with_value`` (of them, those
    with at least one value) and ``assignments`` (their values, one per annotation and value)."""
    query, documents = scope.query, scope.document_ids

    async def count(q: AnnotationQuery) -> int:
        async with limiter:
            return await store.spans.count_rows(cid, q, documents)

    # The tags whose annotations the attribute applies to within the query's own tag filter; None: any tag.
    if attribute.all_tags:
        applicable_tags = list(query.tag_ids) if query.tag_ids else None
    else:
        applicable_tags = [t for t in attribute.tag_ids if not query.tag_ids or t in query.tag_ids]

    async def value(v) -> FacetValue:
        held = query.model_copy(update={"holds_value": codec.encode(attribute.id, v.id)})
        n = await count(held)
        if n == 0 or attribute.all_tags:
            return FacetValue(value=str(v.id), count=n)
        applying = await count(held.model_copy(update={"tag_ids": applicable_tags})) if applicable_tags else 0
        return FacetValue(value=str(v.id), count=n, inapplicable=n - applying)

    async def eligible() -> int:
        if applicable_tags is not None and not applicable_tags or SpanType.pos not in query.types:
            return 0
        return await count(query.model_copy(update={"types": [SpanType.pos], "tag_ids": applicable_tags}))

    async def with_value() -> int:
        if applicable_tags is not None and not applicable_tags or not attribute.values:
            return 0
        # The query's own filter on this attribute already requires one of its values: keep it.
        own = query.attribute_values.get(attribute.id) or [d.id for d in attribute.values]
        return await count(query.model_copy(update={"attribute_values": {**query.attribute_values, attribute.id: own},
                                                    "tag_ids": applicable_tags}))

    unassigned = query.model_copy(update={"attribute_unassigned": [*query.attribute_unassigned, attribute.id]})
    extra = (eligible(), with_value()) if statistics else ()
    answers = await asyncio.gather(*(value(v) for v in attribute.values), count(unassigned), *extra)
    values, (missing, *rest) = answers[:len(attribute.values)], answers[len(attribute.values):]
    shown = [v for v, d in zip(values, attribute.values) if v.count or not d.retired]
    result = Facet(facet=facet, values=shown, missing=missing, total=scope.total)
    if statistics:
        result.eligible, result.with_value = rest
        result.assignments = sum(v.count - v.inapplicable for v in values)
    return result


async def annotation_facets(store: service.AnnotationStore, user: Principal | None, collection_id: service.Id,
                            request: AnnotationFacetsRequest,
                            attributes: "service.AttributeDefinitions | None" = None) -> AnnotationFacets:
    """
    The counts of the choices of each facet in ``request.facets`` for the annotation query (#667); see
    the module. Order: authorization, validation (filters, ranking, attribute facets: 503 on a store
    without attribute properties, 404 for an attribute of another collection), then the reads, the
    provider call of a semantic or hybrid ranking last.

    A facet counts ``total`` annotations, ``missing`` of them without a value (no year, no value of
    the attribute, ...); the values of a single-valued facet add up to ``total`` - ``missing``.
    Lexical queries count every match exactly; ranked queries the top ``k`` as returned.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    ranking = request.ranking
    if ranking.ranked:
        service._check_ranking(store, ranking, None)
        query, text = service._ranking_query(request, ranking)
    else:
        if request.ranking_query:
            raise InvalidRequestError("A similarity text needs a ranked mode (semantic or hybrid).")
        query, text = service._filters_query(request), None
    service._require_attribute_properties(store, query)
    wanted = [UUID(f.partition(":")[2]) for f in request.facets if f.startswith("attribute:")]
    if wanted and not store.spans.attributes:
        raise ServiceUnavailableError(service.ATTRIBUTES_NOT_ENABLED)
    definitions = {}
    for attribute_id in dict.fromkeys(wanted):
        attribute = await attributes.read(grant.collection_id, attribute_id) if attributes is not None else None
        if attribute is None:
            raise NotFoundError("Attribute not found")
        definitions[attribute_id] = attribute
    excluding = request.self_exclusion and not ranking.ranked
    if excluding:
        for facet in request.facets:  # every self-excluded query is valid before any read
            service._filters_query(_without(request, facet))
    cid = await service.use_tenant(store, grant)
    limiter = asyncio.Semaphore(service._MAX_PARTITION_QUERIES)

    if ranking.ranked:
        conditions = document_conditions(request.document_filters)
        query, _ = await service._apply_near(store, cid, request, query, conditions)  # before ranking, as the list
        ranked = await service._rank(store, cid, request, ranking, query, text, conditions)
        everything = service._concordance_query(None, list(SpanType), None, ranked.ids)
        top = _Scope(everything, None, await store.spans.count_rows(cid, everything) if ranked.ids else 0)

        async def scope_of(_: str) -> _Scope:
            return top
    elif excluding:
        async def scope_of(facet: str) -> _Scope:
            return await _lexical_scope(store, cid, _without(request, facet))
    else:
        # One population for every facet (#818), read once before any facet. A refusal of the population
        # itself (a proximity match or document filters over their limits) fails the whole request: it
        # is no empty population, and leaving every facet out would read as zero annotations.
        shared = await _lexical_scope(store, cid, request)

        async def scope_of(_: str) -> _Scope:
            return shared

    async def one(facet: str) -> Facet | None:
        try:
            return await counted(facet)
        except InvalidRequestError:
            # Annotations in more than 10,000 documents: a count that needs the documents cannot be made (the
            # filters of #663 refuse that too), the others still can. Left out; the menu shows no counts.
            # (With self_exclusion false the population is read before, so only such a facet is left out.)
            return None

    async def counted(facet: str) -> Facet:
        scope = await scope_of(facet)
        name = facet.partition(":")[0]
        if name == "attribute":
            return await _by_attribute(store, cid, facet, scope, definitions[UUID(facet.partition(":")[2])], limiter,
                                       statistics=not request.self_exclusion)
        if scope.total == 0:
            return Facet(facet=facet, values=[], missing=0, total=0, **({"distinct": 0} if name == "document" else {}))
        if name in ("tag", "type"):
            return await _by_property(store, cid, name, scope)
        return await _by_document(store, cid, name, scope)

    facets = await asyncio.gather(*(one(f) for f in request.facets))
    return AnnotationFacets(population=FacetPopulation.top_k if ranking.ranked else FacetPopulation.filtered,
                            self_exclusion=excluding, k=ranking.k if ranking.ranked else None,
                            facets=[f for f in facets if f is not None])
