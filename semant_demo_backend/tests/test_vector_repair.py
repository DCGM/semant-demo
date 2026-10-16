"""Offline tests for the temporary, explicitly gated vector repair (#375)."""
import json
from types import SimpleNamespace
from uuid import UUID

from semant_demo.maintenance import vector_repair as repair


def obj(n, *, vector=True):
    return SimpleNamespace(uuid=UUID(int=n), vector={"default": [0.3, 0.7]} if vector else {})


class FakeCollection:
    def __init__(self, objects, fail=None):
        self.objects = objects
        self.updates = []
        self.fail = fail
        self.query = self
        self.data = self

    async def fetch_objects(self, *, limit, after, include_vector, return_properties):
        data = [o for o in self.objects if after is None or o.uuid > after]
        return SimpleNamespace(objects=data[:limit])

    async def update(self, *, uuid, vector):
        if uuid == self.fail:
            raise TimeoutError("temporary")
        self.updates.append((uuid, vector))


async def test_probe_demonstrates_effect_and_emits_targeted_report(monkeypatch, tmp_path):
    collection = FakeCollection([obj(1), obj(2)])
    async def missing(*args, **kwargs):
        return collection.objects

    async def hit(_, candidate, name):
        return candidate.uuid in {id for id, _ in collection.updates}

    monkeypatch.setattr(repair, "_missing_samples", missing)
    monkeypatch.setattr(repair, "_self_hit", hit)
    target = {"endpoint": "localhost:8080", "collection": "Chunks_test", "vector": "default"}
    args = SimpleNamespace(vector="default", sample=2, seed=1, wait_seconds=1,
                           report=str(tmp_path / "probe.json"))
    assert await repair._probe(collection, target, args) == 0
    report = json.loads((tmp_path / "probe.json").read_text())
    assert report["success"] and report["repaired"] == 2
    assert collection.updates == [(obj(1).uuid, {"default": [0.3, 0.7]}),
                                  (obj(2).uuid, {"default": [0.3, 0.7]})]


async def test_probe_refuses_bulk_when_index_does_not_change(monkeypatch, tmp_path):
    collection = FakeCollection([obj(1)])
    async def missing(*args, **kwargs):
        return collection.objects

    async def hit(*args, **kwargs):
        return False

    async def no_sleep(*args):
        pass

    monkeypatch.setattr(repair, "_missing_samples", missing)
    monkeypatch.setattr(repair, "_self_hit", hit)
    monkeypatch.setattr(repair.asyncio, "sleep", no_sleep)
    target = {"endpoint": "localhost:8080", "collection": "Chunks_test", "vector": "default"}
    args = SimpleNamespace(vector="default", sample=1, seed=1, wait_seconds=0,
                           report=str(tmp_path / "probe.json"))
    assert await repair._probe(collection, target, args) == 1
    assert not json.loads((tmp_path / "probe.json").read_text())["success"]


async def test_batches_resume_after_failure_without_advancing_cursor(tmp_path):
    target = {"endpoint": "localhost:8080", "collection": "Chunks_test", "vector": "default"}
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({**target, "type": "vector_repair_probe", "success": True}))
    checkpoint = tmp_path / "state.json"
    args = SimpleNamespace(probe_report=str(probe), checkpoint=str(checkpoint),
                           limit=3, page_size=2, concurrency=2, pause=0, vector="default")
    collection = FakeCollection([obj(1), obj(2), obj(3, vector=False), obj(4)], fail=UUID(int=2))
    assert await repair._run(collection, target, args) == 1
    state = json.loads(checkpoint.read_text())
    assert state["after"] is None and state["scanned"] == 0
    # Two earlier writes may be accepted on the failed page. Retrying is intentional.
    collection.fail = None
    assert await repair._run(collection, target, args) == 0
    state = json.loads(checkpoint.read_text())
    assert state["after"] == str(UUID(int=3))
    assert (state["scanned"], state["rewritten"], state["skipped"]) == (3, 2, 1)
    assert await repair._run(collection, target, args) == 0
    state = json.loads(checkpoint.read_text())
    assert state["complete"] and state["after"] == str(UUID(int=4))
    assert (state["scanned"], state["rewritten"], state["skipped"]) == (4, 3, 1)


async def test_bulk_refuses_unproven_or_wrong_target_probe(tmp_path):
    path = tmp_path / "probe.json"
    state = tmp_path / "state.json"
    target = {"endpoint": "prod:8080", "collection": "Chunks_test", "vector": "default"}
    args = SimpleNamespace(probe_report=str(path), checkpoint=str(state), limit=1,
                           page_size=1, concurrency=1, pause=0, vector="default")
    for payload in ({"type": "vector_repair_probe", "success": False},
                    {**target, "type": "vector_repair_probe", "success": True, "endpoint": "test:8080"}):
        path.write_text(json.dumps(payload))
        import pytest
        with pytest.raises(ValueError):
            await repair._run(FakeCollection([]), target, args)
    assert not state.exists()


def test_cli_requires_explicit_write_confirmation():
    options = repair.parser().parse_args([
        "--confirm-endpoint", "localhost:8080", "probe", "--report", "probe.json"])
    assert not options.execute
    assert repair._vector(obj(1), "missing") is None
    assert repair._vector(obj(2, vector=False), "default") is None
