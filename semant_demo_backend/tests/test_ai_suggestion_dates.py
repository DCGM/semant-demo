"""Date provenance in document AI suggestions (#465 / #460)."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from semant_demo.adapters.weaviate.spans import SpanRepository, to_span
from semant_demo.features.annotations.schemas import TagSpan


def _object(created_at):
    return SimpleNamespace(uuid=uuid4(), properties={
        "chunkId": uuid4(), "tagId": uuid4(), "start": 0, "end": 4,
        "type": "auto", "confidence": 0.8, "createdAt": created_at,
    })


def test_pending_span_returns_only_recorded_creation_time():
    created = datetime(2026, 11, 18, 13, 10, tzinfo=timezone.utc)
    span = to_span(_object(created))
    assert span.createdAt == created
    assert TagSpan.model_validate(span.model_dump(mode="json")).createdAt == created
    assert to_span(_object(None)).createdAt is None


def test_creation_time_is_read_only_when_collection_supports_provenance():
    repo = SpanRepository.__new__(SpanRepository)
    repo.attributes = False
    repo.provenance = False
    assert "createdAt" not in repo._span_properties()
    repo.provenance = True
    assert "createdAt" in repo._span_properties()
