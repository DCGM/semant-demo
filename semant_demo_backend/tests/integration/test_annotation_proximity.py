"""Proximity filters of annotation queries against real Weaviate (#333).

Distances come from the derived document positions (#463): a neighbor in the next chunk is
measured across the chunk boundary; the store's id and document filters restrict counts, pages,
resolved ids and the source list alike; through the API the ``near_`` parameters select the same
annotations and rows name the neighbors that made them match.
"""
from uuid import UUID

import pytest

from semant_demo.features.annotations import service
from semant_demo.features.annotations.schemas import (
    AnnotationFilters, AnnotationIdsRequest, NearDirection, NearFilter, NearRelation, SpanType,
)
from tests.integration.test_annotation_concordance import create, owner, query, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


@pytest.fixture
async def spans(store, owner, ids, corpus):  # noqa: F811
    """Chronicle words: ... do(3) Lhoty(4) hejtman(5) Jan(6) Novák(7) ... jelena.(15) | Kronikář(16) ... Brně(21)."""
    first, second = corpus.chunks["chronicle_1"]["text"], corpus.chunks["chronicle_2"]["text"]
    lhoty, novak, brne = first.index("Lhoty"), first.index("Jan Novák"), second.index("Brně")
    return {
        "novak": await create(store, owner, ids, "chronicle_1", novak, novak + 9),
        "lhoty": await create(store, owner, ids, "chronicle_1", lhoty, lhoty + 5, tag="place"),
        "brne": await create(store, owner, ids, "chronicle_2", brne, brne + 4, tag="place"),
        "hejtman": await create(store, owner, ids, "chronicle_1", lhoty, novak + 9, tag="place"),
    }


def people_near(ids, **kwargs) -> AnnotationFilters:
    return AnnotationFilters(tag_ids=[ids.tag["person"]],
                             near=NearFilter(tag_ids=[ids.tag["place"]], types=[SpanType.pos], **kwargs))


async def found(store, owner, ids, **kwargs) -> set[UUID]:  # noqa: F811
    page = await query(store, owner, ids, people_near(ids, **kwargs), limit=200)
    assert page.total == len(page.rows)
    return {r.id for r in page.rows}


async def test_word_gaps_are_measured_between_boundaries_across_chunks(store, owner, ids, spans):  # noqa: F811
    novak = spans["novak"]
    assert novak in await found(store, owner, ids, distance=1, direction=NearDirection.before)  # Lhoty, hejtman, Jan
    assert novak not in await found(store, owner, ids, distance=12, direction=NearDirection.after)
    assert novak in await found(store, owner, ids, distance=13, direction=NearDirection.after)  # Brně, next chunk


async def test_overlap_and_containment(store, owner, ids, spans):  # noqa: F811
    novak = spans["novak"]
    assert novak in await found(store, owner, ids, relation=NearRelation.overlaps)
    assert novak in await found(store, owner, ids, relation=NearRelation.contained_by)
    assert novak not in await found(store, owner, ids, relation=NearRelation.contains)


async def test_the_filter_applies_before_counting_and_paging(store, owner, ids, spans):  # noqa: F811
    filters = people_near(ids, distance=13)
    full = await query(store, owner, ids, filters, limit=200)
    pages = [r.id for offset in range(full.total) for r in (await query(store, owner, ids, filters, limit=1,
                                                                        offset=offset)).rows]
    assert pages == [r.id for r in full.rows]
    assert spans["novak"] in pages
    novak = next(r for r in full.rows if r.id == spans["novak"])
    assert set(novak.nearIds) <= {spans["lhoty"], spans["brne"], spans["hejtman"]} and novak.nearIds
    assert full.proximity.unknown >= 1  # the seeded person annotation has no derived positions
    resolved = await service.resolve_annotation_ids(store, owner, ids.col["chronicles"],
                                                    AnnotationIdsRequest(**filters.model_dump()))
    assert sorted(resolved.ids, key=str) == sorted(pages, key=str)


async def test_absence_excludes_matches_and_unknown_positions(store, owner, ids, spans):  # noqa: F811
    close = await found(store, owner, ids, distance=13)
    absent = await found(store, owner, ids, distance=13, absent=True)
    assert spans["novak"] not in absent and not close & absent
    seeded = UUID(ids.span["novak_manual"])  # saved without derived positions
    assert seeded not in absent and seeded not in close


async def test_api_takes_the_near_parameters(api_client, login, ids, store, owner, spans):  # noqa: F811
    headers = await login("owner")
    response = await api_client.get(f"/api/user_collections/{ids.col['chronicles']}/annotations", params={
        "tag_id": ids.tag["person"], "near_relation": "within", "near_tag_id": ids.tag["place"], "near_type": "pos",
        "near_distance": 13, "near_direction": "after"}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert spans["novak"] in {UUID(r["id"]) for r in body["rows"]}
    assert body["proximity"]["neighbors"] >= 1
    refused = await api_client.get(f"/api/user_collections/{ids.col['chronicles']}/annotations", params={
        "near_relation": "overlaps", "near_direction": "after"}, headers=headers)
    assert refused.status_code == 422
