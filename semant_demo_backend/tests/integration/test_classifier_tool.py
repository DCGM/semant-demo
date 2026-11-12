"""The classifier (data_tools/meta_data_enrichment, #590) against the test-owned Weaviate.

The real pipeline runs with a fake model: it answers each task with a label chosen per record
(or a configured failure) and records what it was asked. Covers the selection by
``classification_provenance = UNPROCESSED``, missing-only filling, invalid results, the stop
after consecutive failures and after ``max_failures``, the read-only schema, the alias, ``max_records``, the check and the
guarded test collection. Collections are named ``ClassifierToolTest*`` and deleted after
each test, as are aliases to them.
"""
import sys
from pathlib import Path

import pytest
import weaviate
import yaml
from weaviate.classes.config import DataType, Property, Tokenization

sys.path.insert(0, str(Path(__file__).parents[3] / "data_tools" / "meta_data_enrichment"))
from semantmetaenricher.db import (  # noqa: E402
    PROVENANCE, UNPROCESSED, Refused, check_schema, create_test_collection)
from semantmetaenricher.pipeline import EnrichmentPipeline  # noqa: E402

pytestmark = pytest.mark.integration

TEST_COLLECTION = "ClassifierToolTest"
ALIAS = "ClassifierToolTestAlias"
FIELD_TASKS = {"complexity": "complexity", "style": "style"}
LABELS = {"complexity": ["easy", "expert"], "style": ["formal", "informal"]}
PROVENANCE_ID = "test-model-v1"


class FakeModel:
    """Answers ``LABELS[task][0]``; ``failures`` maps a record's text to the value returned for
    every task instead (e.g. None, [] or an unknown label). ``asked`` records (text, tasks)."""

    def __init__(self, failures=None, labels=LABELS):
        self.failures = failures or {}
        self.task_labels = labels
        self.asked: list[tuple[str, tuple[str, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def labels(self, task):
        return self.task_labels.get(task)

    def fingerprint(self):
        return {"cls": "FakeModel"}

    def generate_batch(self, records, tasks):
        results = []
        for record in records:
            self.asked.append((record["text"], tuple(tasks)))
            if record["text"] in self.failures:
                results.append({task: self.failures[record["text"]] for task in tasks})
            else:
                results.append({task: [self.task_labels[task][0]] for task in tasks})
        return results


@pytest.fixture
def client(seeded_store, store_endpoint):
    """A sync client to the owned store (the tool's client type); test collections and the alias
    are deleted afterwards."""
    sync = weaviate.connect_to_local(host=store_endpoint.host, port=store_endpoint.rest_port,
                                     grpc_port=store_endpoint.grpc_port)
    try:
        yield sync
    finally:
        if sync.alias.get(alias_name=ALIAS):
            sync.alias.delete(alias_name=ALIAS)
        for name in sync.collections.list_all(simple=True):
            if name.startswith(TEST_COLLECTION):
                sync.collections.delete(name)
        sync.close()


def create_collection(client, records: list[dict], name: str = TEST_COLLECTION, provenance: bool = True,
                      fields=tuple(FIELD_TASKS)) -> dict[str, str]:
    """A collection as the classifier expects it (unless ``provenance``/``fields`` say otherwise),
    holding ``records``; returns text -> id."""
    client.collections.create(name=name, properties=[
        Property(name="text", data_type=DataType.TEXT),
        *(Property(name=f, data_type=DataType.TEXT_ARRAY) for f in fields),
        *([Property(name=PROVENANCE, data_type=DataType.TEXT, tokenization=Tokenization.FIELD,
                    index_filterable=True, index_searchable=False)] if provenance else []),
    ])
    collection = client.collections.get(name)
    return {record["text"]: str(collection.data.insert(record)) for record in records}


def stored(client, name: str = TEST_COLLECTION) -> dict[str, dict]:
    """text -> properties of every object."""
    return {o.properties["text"]: o.properties
            for o in client.collections.get(name).iterator()}


@pytest.fixture
def make_pipeline(tmp_path, store_endpoint):
    """``make_pipeline(model, **settings)``: a pipeline on the test store with the fake model."""
    def make(model: FakeModel, **settings) -> EnrichmentPipeline:
        config = {
            "weaviate_host": store_endpoint.host, "weaviate_port": store_endpoint.rest_port,
            "weaviate_grpc_port": store_endpoint.grpc_port, "weaviate_api_key": None, "weaviate_headers": None,
            "collection": TEST_COLLECTION, "provenance": PROVENANCE_ID, "field_tasks": FIELD_TASKS,
            "filters": [], "batch_size": 3, "max_records": None, "max_consecutive_failures": 5,
            "max_failures": 100, "max_retries": 0, "retry_delay": 0.0,
            "model": {"cls": "LocalHFClassifierModel", "config": {
                "model_path": "unused/", "device": "cpu", "input_prompt": "{{ text }}", "threshold": 0.5}},
            **settings,
        }
        path = tmp_path / "classifier.yaml"
        path.write_text(yaml.safe_dump(config))
        pipeline = EnrichmentPipeline.create(str(path))
        pipeline.model = model
        return pipeline
    return make


def unprocessed(*texts: str, **fields) -> list[dict]:
    return [{"text": t, PROVENANCE: UNPROCESSED, **fields} for t in texts]


def test_a_run_classifies_every_unprocessed_chunk_and_sets_the_provenance(client, make_pipeline):
    texts = [f"chunk {i}" for i in range(7)]
    create_collection(client, unprocessed(*texts))
    model = FakeModel()

    result = make_pipeline(model).run()

    assert (result.selected, result.classified, result.filled, result.remaining, result.failed) == (7, 7, 14, 0, [])
    assert result.exit_code() == 0 and result.model == {"cls": "FakeModel"}
    for properties in stored(client).values():
        assert properties["complexity"] == ["easy"] and properties["style"] == ["formal"]
        assert properties[PROVENANCE] == PROVENANCE_ID
    assert sorted(text for text, _ in model.asked) == sorted(texts)


def test_chunks_without_the_status_value_or_already_classified_are_never_selected(client, make_pipeline):
    create_collection(client, [
        *unprocessed("new"),
        {"text": "before the property", "complexity": [], "style": None},
        {"text": "classified", PROVENANCE: "older-model", "complexity": ["expert"], "style": ["informal"]},
    ])
    model = FakeModel()

    result = make_pipeline(model).run()

    assert (result.selected, result.classified) == (1, 1)
    after = stored(client)
    assert after["before the property"].get(PROVENANCE) is None and after["before the property"]["complexity"] == []
    assert after["classified"][PROVENANCE] == "older-model" and after["classified"]["complexity"] == ["expert"]
    assert [text for text, _ in model.asked] == ["new"]


def test_only_missing_fields_are_computed_and_existing_values_kept(client, make_pipeline):
    create_collection(client, [
        *unprocessed("partly", complexity=["expert"]),
        *unprocessed("empty list", complexity=[], style=None),
        *unprocessed("complete", complexity=["expert"], style=["informal"]),
    ])
    model = FakeModel()

    result = make_pipeline(model).run()

    assert (result.classified, result.filled, result.remaining) == (3, 3, 0)
    after = stored(client)
    assert after["partly"]["complexity"] == ["expert"] and after["partly"]["style"] == ["formal"]
    assert after["empty list"]["complexity"] == ["easy"] and after["empty list"]["style"] == ["formal"]
    assert after["complete"]["complexity"] == ["expert"] and after["complete"]["style"] == ["informal"]
    assert all(p[PROVENANCE] == PROVENANCE_ID for p in after.values())
    asked = dict(model.asked)
    assert asked["partly"] == ("style",) and asked["empty list"] == ("complexity", "style")
    assert "complete" not in asked  # nothing missing: only the provenance is written


@pytest.mark.parametrize("failure", [None, [], ["not a label"]])
def test_a_chunk_without_a_valid_result_is_not_written_and_stays_unprocessed(client, make_pipeline, failure):
    ids = create_collection(client, unprocessed("good 1", "bad", "good 2", complexity=["expert"]))

    result = make_pipeline(FakeModel(failures={"bad": failure})).run()

    assert (result.classified, result.failed, result.remaining) == (2, [ids["bad"]], 1)
    assert result.exit_code() == 1
    after = stored(client)
    assert after["bad"][PROVENANCE] == UNPROCESSED and after["bad"]["style"] is None
    assert after["good 1"][PROVENANCE] == after["good 2"][PROVENANCE] == PROVENANCE_ID


def test_failed_chunks_do_not_hide_others_across_pages(client, make_pipeline):
    texts = [f"chunk {i:02}" for i in range(11)]
    failing = {t: None for t in texts[::3]}  # 4 failures spread over the pages of 3
    create_collection(client, unprocessed(*texts))
    model = FakeModel(failures=failing)

    result = make_pipeline(model).run()

    assert (result.classified, len(result.failed), result.remaining) == (7, 4, 4)
    assert {t for t, p in stored(client).items() if p[PROVENANCE] == PROVENANCE_ID} == set(texts) - set(failing)
    assert sorted(t for t, _ in model.asked) == sorted(texts)  # every chunk asked exactly once


def test_a_run_stops_after_consecutive_failures(client, make_pipeline):
    texts = [f"chunk {i:02}" for i in range(10)]
    create_collection(client, unprocessed(*texts))
    model = FakeModel(failures={t: None for t in texts})

    result = make_pipeline(model, max_consecutive_failures=4).run()

    assert result.stopped == "4 consecutive chunks failed" and len(result.failed) == 4
    assert (result.classified, result.remaining, result.exit_code()) == (0, 10, 1)
    assert len(model.asked) <= 6  # the page that hit the limit, at most
    assert all(p[PROVENANCE] == UNPROCESSED for p in stored(client).values())


def test_a_run_stops_after_max_failures_in_total(client, make_pipeline):
    texts = [f"chunk {i:02}" for i in range(12)]
    failing = {t: None for t in texts[::2]}  # 6 failures; the store's order decides how they interleave
    ids = create_collection(client, unprocessed(*texts))
    model = FakeModel(failures=failing)

    result = make_pipeline(model, max_consecutive_failures=100, max_failures=3).run()

    assert result.stopped == "max_failures (3) reached" and len(result.failed) == 3
    assert set(result.failed) <= {ids[t] for t in failing}
    assert result.remaining == 12 - result.classified and result.exit_code() == 1
    assert len(model.asked) < 12  # stopped before the selection was exhausted
    after = stored(client)
    assert {t for t, p in after.items() if p[PROVENANCE] == PROVENANCE_ID} <= set(texts) - set(failing)
    assert all(after[t][PROVENANCE] == UNPROCESSED for t in failing)


def test_max_records_bounds_a_run(client, make_pipeline):
    create_collection(client, unprocessed(*[f"chunk {i}" for i in range(8)]))

    result = make_pipeline(FakeModel(), max_records=5).run()

    assert (result.classified, result.remaining, result.stopped) == (5, 3, "max_records (5) reached")
    assert result.exit_code() == 1


def test_filters_narrow_the_selection(client, make_pipeline):
    create_collection(client, unprocessed("keep me", "other"))

    result = make_pipeline(FakeModel(), filters=[{"property": "text", "operator": "like", "value": "keep*"}]).run()

    assert (result.selected, result.classified, result.remaining) == (1, 1, 0)
    assert stored(client)["other"][PROVENANCE] == UNPROCESSED


def test_a_collection_behind_an_alias_is_resolved(client, make_pipeline):
    create_collection(client, unprocessed("aliased"))
    client.alias.create(alias_name=ALIAS, target_collection=TEST_COLLECTION)

    result = make_pipeline(FakeModel(), collection=ALIAS).run()

    assert (result.collection, result.classified) == (TEST_COLLECTION, 1)


@pytest.mark.parametrize("setup, settings, reason", [
    (dict(provenance=False), {}, f"'{PROVENANCE}' is not declared"),
    (dict(fields=("complexity",)), {}, "field 'style' is not declared"),
    (dict(), {"collection": "ClassifierToolTestMissing"}, "does not exist"),
    (dict(), {"filters": [{"property": "style", "operator": "equal", "value": "formal"}]}, "Filters cannot include"),
    (dict(), {"filters": [{"property": PROVENANCE, "operator": "equal", "value": "x"}]}, "Filters cannot include"),
])
def test_a_refused_run_changes_nothing(client, make_pipeline, setup, settings, reason):
    create_collection(client, unprocessed("chunk") if setup.get("provenance", True) else [{"text": "chunk"}], **setup)
    before = client.collections.get(TEST_COLLECTION).config.get().properties
    model = FakeModel()

    result = make_pipeline(model, **settings).run()

    assert reason in result.refused and result.exit_code() == 2
    assert model.asked == [] and client.collections.get(TEST_COLLECTION).config.get().properties == before
    assert stored(client)["chunk"].get("style") is None


def test_a_model_without_a_mapped_task_is_refused(client, make_pipeline):
    create_collection(client, unprocessed("chunk"))
    model = FakeModel(labels={"complexity": ["easy"]})

    result = make_pipeline(model).run()

    assert "['style']" in result.refused and model.asked == []
    assert stored(client)["chunk"][PROVENANCE] == UNPROCESSED


def test_a_differently_declared_status_is_refused(client):
    client.collections.create(name=TEST_COLLECTION, properties=[
        Property(name="text", data_type=DataType.TEXT),
        *(Property(name=f, data_type=DataType.TEXT_ARRAY) for f in FIELD_TASKS),
        Property(name=PROVENANCE, data_type=DataType.TEXT, tokenization=Tokenization.WORD)])

    with pytest.raises(Refused, match="field tokenization"):
        check_schema(client, TEST_COLLECTION, list(FIELD_TASKS))


def test_the_check_counts_without_writing(client, make_pipeline):
    create_collection(client, unprocessed("a", "b"))
    model = FakeModel()

    result = make_pipeline(model).check()

    assert (result.selected, result.remaining, result.exit_code()) == (2, 2, 1)
    assert model.asked == [] and all(p[PROVENANCE] == UNPROCESSED for p in stored(client).values())
    assert "not declared" in make_pipeline(model, field_tasks={"missing": "complexity"}).check().refused


def test_the_test_collection_is_ready_for_a_run_and_guarded(client, make_pipeline):
    create_test_collection(client, list(FIELD_TASKS), collection_name=TEST_COLLECTION)

    assert check_schema(client, TEST_COLLECTION, list(FIELD_TASKS)) == TEST_COLLECTION
    with pytest.raises(Refused, match="already exists"):
        create_test_collection(client, list(FIELD_TASKS), collection_name=TEST_COLLECTION)
    result = make_pipeline(FakeModel()).run()
    assert (result.selected, result.classified, result.remaining) == (10, 10, 0)

    create_test_collection(client, list(FIELD_TASKS), replace=True, collection_name=TEST_COLLECTION)
    assert all(p[PROVENANCE] == UNPROCESSED for p in stored(client).values()) and len(stored(client)) == 10
