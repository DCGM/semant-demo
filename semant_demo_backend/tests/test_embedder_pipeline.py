"""The offline embedder's selection when Weaviate's filter lags behind a write (data_tools/embedder, #816).

A run reads the first page of the records whose ``haveVector`` lacks the vector's name again
and again. Under load the filter can still match a record written moments ago while the record
read already lists the name (and stores the vector): such a record must be left alone, not
embedded again nor its name added a second time. The full pipeline runs against Weaviate in
``tests/integration/test_embedder_tool.py``.
"""
import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import yaml
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parents[2] / "data_tools" / "embedder"))
from semantembedder.pipeline import EmbeddingPipeline, PipelineStats  # noqa: E402

from tests.test_embedder_cli import CONFIG  # noqa: E402

NAME = CONFIG["vector_name"]


class Collection:
    """Records the writes (``data.update``) of a run."""

    def __init__(self):
        self.updates = []
        self.data = SimpleNamespace(update=self.update)

    async def update(self, uuid, properties, vector=None):
        self.updates.append((uuid, properties, vector))


def pipeline(tmp_path) -> EmbeddingPipeline:
    path = tmp_path / "embedder.yaml"
    path.write_text(yaml.safe_dump(CONFIG))
    return EmbeddingPipeline.create(str(path))


def record(listed, stored: bool, text: str = "Some text"):
    return SimpleNamespace(uuid=uuid.uuid4(), properties={"text": text, "haveVector": listed},
                           vector={NAME: [0.1, 0.2]} if stored else {})


async def test_a_record_selected_again_just_after_its_write_is_left_alone(tmp_path, monkeypatch):
    stale = record(["default", NAME], stored=True)  # written: the filter has not caught up yet
    stored = record(["default"], stored=True)  # stores the vector: gets only the name
    fresh = record(["default"], stored=False)  # to embed

    async def select(self, collection, excluded, stats, include_vector=True, done=None):
        yield [stale, stored, fresh]

    monkeypatch.setattr(EmbeddingPipeline, "_select", select)
    tool, collection, queue, stats, excluded = pipeline(tmp_path), Collection(), asyncio.Queue(), PipelineStats(), set()
    await tool._produce(collection, queue, asyncio.Semaphore(1), tqdm(disable=True), stats, excluded)

    assert collection.updates == [(stored.uuid, {"haveVector": ["default", NAME]}, None)]
    batch = await queue.get()
    assert batch[0] == [fresh.uuid] and batch[2] == [["default"]]
    assert (stats.selected, stats.stale, stats.already_stored) == (2, 1, 1)
    assert stale.uuid in excluded  # not read again in this run


async def test_a_write_never_lists_the_name_twice(tmp_path):
    tool, collection = pipeline(tmp_path), Collection()
    record_id = uuid.uuid4()
    await tool._write(collection, record_id, ["default", NAME], [0.5], asyncio.Semaphore(1))
    await tool._write(collection, record_id, None, None, asyncio.Semaphore(1))
    assert [update[1] for update in collection.updates] == [{"haveVector": ["default", NAME]}, {"haveVector": [NAME]}]
