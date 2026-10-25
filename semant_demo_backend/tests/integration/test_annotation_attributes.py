"""Collection attributes against real Weaviate (#331, ADR 0011).

The stored assignments are exact whole elements ``<attribute id>:<value id>`` of
``Annotation.attributeValues``: filters match similar ids, several values, empty arrays and
annotations that never had the property without accidental hits, and "no value of attribute A"
is the explicit negation of A's fixed-length prefix. Through the API: definitions per collection,
assignment with ``attributeVersion`` conflicts, eligibility (approved annotations only), tag
applicability, cross-collection ids, value retirement, deletion of used definitions, and a
collection without the attribute properties (which must not get them from Weaviate's
auto-schema) refusing assignments.
"""
from uuid import UUID

import pytest

from semant_demo.adapters.weaviate.spans import (
    ATTRIBUTE_PROPERTIES, SpanRepository, add_attribute_schema, attribute_schema,
)
from semant_demo.features.annotations.schemas import AnnotationQuery, SpanType
from semant_demo.features.annotations import attribute_codec as codec

pytestmark = pytest.mark.integration

A1 = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa01")
A2 = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa02")  # differs from A1 in the last character only
V1 = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb01")
V2 = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb02")
V3 = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbb03")
ALL_TYPES = [SpanType.pos, SpanType.auto, SpanType.neg]


def _query(**kwargs) -> AnnotationQuery:
    return AnnotationQuery(types=ALL_TYPES, **kwargs)


async def _matching(spans: SpanRepository, collection: UUID, **kwargs) -> set[str]:
    rows = await spans.query_rows(collection, _query(**kwargs), by_text=False, limit=100)
    return {str(r.id) for r in rows}


async def test_filters_match_exact_elements_not_similar_ids_empty_arrays_or_missing_properties(
        spans, ids, corpus):
    spans.attributes = True
    collection = UUID(ids.col["chronicles"])
    novak, brno, rejected, lhota, praha = (UUID(ids.span[k]) for k in (
        "novak_manual", "brno_manual", "kronikar_rejected", "lhota_automatic", "praha_automatic"))
    await spans.write_attributes(collection, novak, [codec.encode(A1, V1)], 1)
    await spans.write_attributes(collection, brno, [codec.encode(A1, V1), codec.encode(A2, V3)], 1)
    await spans.write_attributes(collection, rejected, [], 2)  # cleared: an empty array
    # lhota and praha never had the properties.

    assert await _matching(spans, collection, attribute_values={A1: [V1]}) == {str(novak), str(brno)}
    assert await _matching(spans, collection, attribute_values={A1: [V2]}) == set()
    assert await _matching(spans, collection, attribute_values={A2: [V1]}) == set()  # a similar attribute id
    assert await _matching(spans, collection, attribute_values={A1: [V1, V2]}) == {str(novak), str(brno)}
    assert await _matching(spans, collection, attribute_values={A1: [V1], A2: [V3]}) == {str(brno)}
    assert await _matching(spans, collection, attribute_values={A2: [V3]}) == {str(brno)}

    # No accepted value of A1: the empty array and the never written property count, A2 is no A1.
    assert await _matching(spans, collection, attribute_unassigned=[A1]) == {str(rejected), str(lhota), str(praha)}
    assert await _matching(spans, collection, attribute_unassigned=[A2]) == {
        str(novak), str(rejected), str(lhota), str(praha)}
    assert await _matching(spans, collection, attribute_unassigned=[A1, A2]) == {
        str(rejected), str(lhota), str(praha)}
    assert await _matching(spans, collection, attribute_values={A2: [V3]}, attribute_unassigned=[A1]) == set()

    # Other tenants are untouched.
    assert await _matching(spans, UUID(ids.col["newspapers"]), attribute_values={A1: [V1]}) == set()


async def test_use_counts_per_attribute_and_value(spans, ids):
    spans.attributes = True
    collection = UUID(ids.col["chronicles"])
    await spans.write_attributes(collection, UUID(ids.span["novak_manual"]), [codec.encode(A1, V1)], 1)
    await spans.write_attributes(collection, UUID(ids.span["brno_manual"]),
                                 [codec.encode(A1, V2), codec.encode(A2, V3)], 1)

    assert await spans.count_attribute_use(collection, A1) == 2
    assert await spans.count_attribute_use(collection, A1, V1) == 1
    assert await spans.count_attribute_use(collection, A1, V3) == 0
    assert await spans.count_attribute_use(collection, A2) == 1


async def _define(api_client, headers, collection, **body):
    response = await api_client.post(f"/api/user_collections/{collection}/attributes", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _assign(collection, **body):
    return f"/api/user_collections/{collection}/annotations/attributes/assign", body


async def _rows(api_client, headers, collection, **params):
    response = await api_client.get(f"/api/user_collections/{collection}/annotations", headers=headers,
                                    params={"type": ["pos", "auto", "neg"], "limit": 200, **params})
    assert response.status_code == 200, response.text
    return {r["id"]: r for r in response.json()["rows"]}


async def test_definitions_are_per_collection_and_assignments_are_exact_and_versioned(api_client, login, ids):
    owner, annotator, outsider = await login("owner"), await login("annotator"), await login("outsider")
    collection, other = ids.col["chronicles"], ids.col["newspapers"]
    novak, brno, lhota = ids.span["novak_manual"], ids.span["brno_manual"], ids.span["lhota_automatic"]

    speaker = await _define(api_client, owner, collection, name="speaker_type", cardinality="single", values=[
        {"label": 'Narrator "I": (1st)'}, {"label": "Author"}, {"label": "Unknown", "kind": "unknown"}])
    topic = await _define(api_client, annotator, collection, name="topic", cardinality="multi",
                          values=[{"label": "war"}, {"label": "weather"}])  # a shared user defines too
    values = {v["label"]: v["id"] for v in speaker["values"]}
    topics = {v["label"]: v["id"] for v in topic["values"]}
    # Names are unique per collection, ignoring case; another collection may reuse them.
    taken = await api_client.post(f"/api/user_collections/{collection}/attributes", headers=owner,
                                  json={"name": " Speaker_Type "})
    assert taken.status_code == 400
    await _define(api_client, owner, other, name="speaker_type")
    # Outsiders neither read nor define.
    assert (await api_client.get(f"/api/user_collections/{collection}/attributes", headers=outsider)).status_code == 404
    assert (await api_client.post(f"/api/user_collections/{collection}/attributes", headers=outsider,
                                  json={"name": "x"})).status_code == 404

    url, body = _assign(collection, attribute_id=speaker["id"], annotation_ids=[novak, brno, lhota],
                        expected_versions={novak: 0, brno: 0, lhota: 0}, mode="replace",
                        value_ids=[values["Author"]])
    result = (await api_client.post(url, headers=annotator, json=body)).json()
    # The unresolved AI suggestion takes no value; the approved ones do.
    assert sorted(result["succeeded"]) == sorted([novak, brno])
    assert [(f["item_id"], f["step"]) for f in result["failed"]] == [(lhota, "check_annotation_type")]
    assert result["outcome"] == "partial" and result["versions"] == {novak: 1, brno: 1}

    rows = await _rows(api_client, owner, collection)
    assert rows[novak]["attributes"] == {speaker["id"]: [values["Author"]]}
    assert rows[novak]["attributeVersion"] == 1 and rows[lhota]["attributes"] == {}
    # Attribute changes never touch the annotation's own version (ADR 0011).
    assert rows[novak]["editVersion"] == 0

    # Exact filters through the API; "unassigned" and "any of" combine with the usual filters.
    has = lambda r: set(r)  # noqa: E731
    assert has(await _rows(api_client, owner, collection, attribute=f"{speaker['id']}:{values['Author']}")) \
        == {novak, brno}
    assert has(await _rows(api_client, owner, collection, attribute=f"{speaker['id']}:{values['Unknown']}")) == set()
    assert has(await _rows(api_client, owner, collection, unassigned=speaker["id"])) \
        >= {lhota, ids.span["kronikar_rejected"]}
    assert not has(await _rows(api_client, owner, collection, unassigned=speaker["id"])) & {novak, brno}

    # A single-valued attribute: adding a different value is refused, replacing is not; a multi-valued
    # one accumulates, and removing works.
    url, body = _assign(collection, attribute_id=speaker["id"], annotation_ids=[novak], expected_versions={novak: 1},
                        mode="add", value_ids=[values["Unknown"]])
    refused = (await api_client.post(url, headers=owner, json=body)).json()
    assert [f["step"] for f in refused["failed"]] == ["check_cardinality"]
    url, body = _assign(collection, attribute_id=speaker["id"], annotation_ids=[novak], expected_versions={novak: 1},
                        mode="replace", value_ids=[values["Unknown"]])
    assert (await api_client.post(url, headers=owner, json=body)).json()["succeeded"] == [novak]
    for label in ("war", "weather"):
        url, body = _assign(collection, attribute_id=topic["id"], annotation_ids=[brno],
                            expected_versions={brno: (await _rows(api_client, owner, collection))[brno]
                                               ["attributeVersion"]}, mode="add", value_ids=[topics[label]])
        assert (await api_client.post(url, headers=owner, json=body)).json()["succeeded"] == [brno]
    brno_row = (await _rows(api_client, owner, collection))[brno]
    assert sorted(brno_row["attributes"][topic["id"]]) == sorted(topics.values())
    assert brno_row["attributes"][speaker["id"]] == [values["Author"]]  # the other attribute is kept

    # Stale: the owner still has brno at version 1; it is at 3 now. Nothing changes.
    url, body = _assign(collection, attribute_id=topic["id"], annotation_ids=[brno], expected_versions={brno: 1},
                        mode="remove", value_ids=[topics["war"]])
    stale = (await api_client.post(url, headers=owner, json=body)).json()
    assert [f["step"] for f in stale["failed"]] == ["edit_conflict"] and stale["versions"] == {brno: 3}
    assert sorted(stale["values"][brno]) == sorted(topics.values())

    # Contradictory values and values of another attribute or collection are refused up front.
    url, body = _assign(collection, attribute_id=speaker["id"], annotation_ids=[brno], expected_versions={brno: 3},
                        mode="replace", value_ids=[values["Author"], values["Unknown"]])
    assert (await api_client.post(url, headers=owner, json=body)).status_code == 400
    url, body = _assign(collection, attribute_id=speaker["id"], annotation_ids=[brno], expected_versions={brno: 3},
                        mode="replace", value_ids=[topics["war"]])
    assert (await api_client.post(url, headers=owner, json=body)).status_code == 404
    url, body = _assign(collection, attribute_id=(await _define(api_client, owner, other, name="foreign"))["id"],
                        annotation_ids=[brno], expected_versions={brno: 3}, mode="add",
                        value_ids=[values["Author"]])
    assert (await api_client.post(url, headers=owner, json=body)).status_code == 404

    # Every change is recorded with who made it, what it replaced (with the names of that time),
    # and the versions it saw; renaming the definitions afterwards does not rewrite the history.
    base = f"/api/user_collections/{collection}"
    assert (await api_client.patch(f"{base}/attributes/{speaker['id']}", headers=owner,
                                   json={"name": "voice"})).status_code == 200
    assert (await api_client.patch(f"{base}/attributes/{speaker['id']}/values/{values['Author']}", headers=owner,
                                   json={"label": "Writer"})).status_code == 200
    changes = (await api_client.get(f"{base}/annotations/{novak}/attribute-changes", headers=owner)).json()
    author = {"id": values["Author"], "label": "Author", "kind": "value"}
    unknown = {"id": values["Unknown"], "label": "Unknown", "kind": "unknown"}
    assert [(c["actor_id"], c["attribute_name"], c["previous"], c["current"], c["source"]) for c in changes] == [
        (ids.user["annotator"], "speaker_type", [], [author], "manual"),
        (ids.user["owner"], "speaker_type", [author], [unknown], "manual")]


async def test_tags_can_limit_an_attribute_and_retired_or_used_definitions_are_kept(api_client, login, ids):
    owner = await login("owner")
    collection = ids.col["chronicles"]
    novak, brno = ids.span["novak_manual"], ids.span["brno_manual"]  # a person and a place
    only_places = await _define(api_client, owner, collection, name="place_kind", tag_ids=[ids.tag["place"]],
                                values=[{"label": "city"}, {"label": "village"}])
    city, village = (v["id"] for v in only_places["values"])
    assert (await api_client.post(f"/api/user_collections/{collection}/attributes", headers=owner, json={
        "name": "bad", "tag_ids": [ids.tag["event"]]})).status_code == 404  # a tag of another collection

    url, body = _assign(collection, attribute_id=only_places["id"], annotation_ids=[novak, brno],
                        expected_versions={novak: 0, brno: 0}, mode="add", value_ids=[city])
    result = (await api_client.post(url, headers=owner, json=body)).json()
    assert result["succeeded"] == [brno]
    assert [(f["item_id"], f["step"]) for f in result["failed"]] == [(novak, "check_applicable")]

    # Used values and attributes are not deleted (409 with the number affected) but can be retired.
    base = f"/api/user_collections/{collection}/attributes/{only_places['id']}"
    in_use = await api_client.delete(f"{base}/values/{city}", headers=owner)
    assert (in_use.status_code, in_use.json()["affected"]) == (409, 1)
    assert (await api_client.delete(base, headers=owner)).status_code == 409
    assert (await api_client.delete(f"{base}/values/{village}", headers=owner)).status_code == 200
    retired = await api_client.patch(f"{base}/values/{city}", headers=owner, json={"retired": True, "label": "City"})
    assert retired.status_code == 200
    assert [(v["label"], v["retired"]) for v in retired.json()["values"]] == [("City", True)]

    # Renamed: the stored assignment is untouched; a retired value is not assigned again.
    row = (await _rows(api_client, owner, collection))[brno]
    assert row["attributes"] == {only_places["id"]: [city]}
    url, body = _assign(collection, attribute_id=only_places["id"], annotation_ids=[ids.span["pozar_manual"]],
                        expected_versions={ids.span["pozar_manual"]: 0}, mode="add", value_ids=[city])
    # An annotation of another collection is not found in this one's tenant.
    assert (await api_client.post(url, headers=owner, json=body)).json()["failed"][0]["step"] == "find_annotation"
    url, body = _assign(collection, attribute_id=only_places["id"], annotation_ids=[brno],
                        expected_versions={brno: 1}, mode="remove", value_ids=[city])
    assert (await api_client.post(url, headers=owner, json=body)).json()["succeeded"] == [brno]
    assert (await api_client.delete(base, headers=owner)).status_code == 204


async def test_a_collection_without_the_attribute_properties_refuses_assignments_and_gets_them_added(
        api_client, api_app, login, ids, seeded_store, collection_names):
    owner = await login("owner")
    collection, novak = ids.col["chronicles"], ids.span["novak_manual"]
    attribute = await _define(api_client, owner, collection, name="speaker_type", values=[{"label": "Author"}])
    value = attribute["values"][0]["id"]

    annotations = seeded_store.collections.get(collection_names.annotation_collection_name)
    config = await annotations.config.get()
    assert {p.name for p in ATTRIBUTE_PROPERTIES} <= {p.name for p in config.properties}
    assert await attribute_schema(seeded_store, collection_names) == []
    # Simulate a store created before #331 by turning the backend's startup decision off.
    api_app.state.resources.weaviate.spans.attributes = False
    url, body = _assign(collection, attribute_id=attribute["id"], annotation_ids=[novak],
                        expected_versions={novak: 0}, mode="add", value_ids=[value])
    refused = await api_client.post(url, headers=owner, json=body)
    assert refused.status_code == 503 and "add-schema" in refused.json()["detail"]
    # Attribute filters would fail on the undeclared property: they are refused the same way.
    list_url = f"/api/user_collections/{collection}/annotations"
    for params in ({"attribute": f"{attribute['id']}:{value}"}, {"unassigned": attribute["id"]}):
        filtered = await api_client.get(list_url, headers=owner, params=params)
        assert filtered.status_code == 503 and "add-schema" in filtered.json()["detail"]
    assert (await api_client.get(list_url, headers=owner)).status_code == 200
    # Definitions keep working; adding the properties again changes nothing.
    assert (await api_client.get(f"/api/user_collections/{collection}/attributes", headers=owner)).status_code == 200
    assert await add_attribute_schema(seeded_store, collection_names) == []
    assert (await _rows(api_client, owner, collection))[novak]["attributes"] == {}


async def test_deleting_a_collection_removes_its_definitions(api_client, login, ids):
    owner = await login("owner")
    collection = ids.col["newspapers"]
    attribute = await _define(api_client, owner, collection, name="topic")
    assert (await api_client.delete(f"/api/user_collections/{collection}", headers=owner)).status_code == 204
    # The definitions went with it, not just became unreachable.
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from semant_demo.adapters.sql.attributes import AttributeRow
    engine = create_async_engine(api_client._transport.app.state.config.SQL_DB_URL)
    try:
        async with async_sessionmaker(engine)() as session:
            assert (await session.execute(select(AttributeRow).where(AttributeRow.id == attribute["id"]))
                    ).scalar_one_or_none() is None
    finally:
        await engine.dispose()


async def test_values_kept_on_a_rejected_annotation_are_hidden_and_assignments_do_not_re_embed(api_client, login, ids):
    owner = await login("owner")
    collection, brno = ids.col["chronicles"], ids.span["brno_manual"]
    attribute = await _define(api_client, owner, collection, name="stance", values=[{"label": "for"}])
    value = attribute["values"][0]["id"]
    before = (await _rows(api_client, owner, collection))[brno]

    url, body = _assign(collection, attribute_id=attribute["id"], annotation_ids=[brno],
                        expected_versions={brno: 0}, mode="add", value_ids=[value])
    assert (await api_client.post(url, headers=owner, json=body)).json()["succeeded"] == [brno]
    after = (await _rows(api_client, owner, collection))[brno]
    # An attribute change moves neither the annotation's revision nor its derived text (ADR 0009).
    assert (after["revision"], after["textStatus"], after["text"]) == \
        (before["revision"], before["textStatus"], before["text"])
    assert after["attributes"] == {attribute["id"]: [value]}

    async def review(action):
        row = (await _rows(api_client, owner, collection))[brno]
        response = await api_client.post(
            f"/api/user_collections/{collection}/annotations/review", headers=owner,
            json={"action": action, "annotation_ids": [brno], "expected_versions": {brno: row["editVersion"]}})
        assert response.json()["succeeded"] == [brno], response.text

    await review("reject")
    # The value is still stored, but a rejected annotation is no accepted classification.
    assert (await _rows(api_client, owner, collection))[brno]["attributes"] == {}
    # The document view's spans never carry values, of any type (only rows show them, approved only).
    spans = (await api_client.get("/api/tag_spans", headers=owner, params={"collection_id": collection})).json()
    rejected = next(s for s in spans if s["id"] == brno)
    assert rejected["type"] == "neg" and "attributes" not in rejected and rejected["attributeVersion"] == 1
    assert brno not in await _rows(api_client, owner, collection, attribute=f"{attribute['id']}:{value}")
    assert brno in await _rows(api_client, owner, collection, unassigned=attribute["id"])

    await review("approve")
    assert (await _rows(api_client, owner, collection))[brno]["attributes"] == {attribute["id"]: [value]}
    assert brno in await _rows(api_client, owner, collection, attribute=f"{attribute['id']}:{value}")
