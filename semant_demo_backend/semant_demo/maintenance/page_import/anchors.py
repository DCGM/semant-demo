"""The ``anchors`` step: bring the stored ``Chunks.layoutStart`` in line with the anchor plans.

For each document of the asset store it reads the anchor plan written by the ``assets`` step
and the document's stored chunks, and decides per planned chunk:

* ``unchanged``: the stored anchor already equals the planned one (or both are absent);
* ``set``: store the planned anchor; ``clear``: the plan has none (unverified), so a stored
  one is removed, and the chunk falls back to text-only;
* ``text_changed``: the stored text is not the text the plan was made from: left alone
  (rerun the ``assets`` step); ``chunk_missing``: the chunk no longer exists.

A stored anchor on a chunk that the plan does not list is reported (``unplanned_anchor``) and
left. A plan whose parameters are not the manifest's (the page files would not match) is
refused for the whole document. Only ``set``/``clear`` are written (a merge of
``layoutStart`` alone), then read back. Running again is safe: written chunks are then
``unchanged``.
"""
import asyncio
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from pydantic import ValidationError

from semant_demo.adapters.filesystem.page_assets import InvalidManifest, PageAssetStore
from semant_demo.adapters.weaviate.layout_anchors import AnchoredChunk
from semant_demo.features.documents.schemas import LayoutStart
from semant_demo.maintenance.page_import.assets import Issues, plan_path, text_sha

WRITES = ("set", "clear")


class AnchorStore(Protocol):
    async def read_chunks(self, document_id: UUID) -> list[AnchoredChunk]: ...
    async def write(self, chunk_id: UUID, value: dict[str, Any] | None) -> None: ...
    async def read_back(self, ids: Sequence[UUID]) -> dict[UUID, dict[str, Any] | None]: ...


def normalized(value: Any) -> dict[str, Any] | None:
    """A stored or planned anchor as comparable JSON; an invalid one compares as ``invalid``."""
    if value is None:
        return None
    try:
        return LayoutStart.model_validate(value).model_dump(mode="json")
    except ValidationError:
        return {"invalid": True}


@dataclass
class DocumentPlan:
    document_id: UUID
    status: str
    """``planned``, or why nothing is done: ``no_manifest``, ``no_plan``, ``unreadable_plan``,
    ``params_mismatch``, ``read_failed``."""
    actions: list[tuple[UUID, str, dict[str, Any] | None]] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    issues: Issues = field(default_factory=Issues)


def read_plan(store: PageAssetStore, document_id: UUID) -> list[dict[str, Any]] | None:
    path = plan_path(store, document_id)
    if not path.is_file():
        return None
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def plan_document(store: PageAssetStore, document_id: UUID, chunks: list[AnchoredChunk] | None) -> DocumentPlan:
    """Decide the writes of one document (``chunks``: its stored chunks; None: unreadable)."""
    try:
        manifest = store.read_manifest(document_id)
    except InvalidManifest:
        manifest = None
    if manifest is None:
        return DocumentPlan(document_id, "no_manifest")
    try:
        plan = read_plan(store, document_id)
    except (OSError, ValueError):
        return DocumentPlan(document_id, "unreadable_plan")
    if plan is None:
        return DocumentPlan(document_id, "no_plan")
    if any(line.get("params") != manifest.params for line in plan):
        return DocumentPlan(document_id, "params_mismatch")
    if chunks is None:
        return DocumentPlan(document_id, "read_failed")

    result = DocumentPlan(document_id, "planned")
    stored = {c.id: c for c in chunks}
    planned_ids = set()
    for line in plan:
        chunk_id = UUID(line["chunkId"])
        planned_ids.add(chunk_id)
        chunk = stored.get(chunk_id)
        if chunk is None:
            result.counts["chunk_missing"] += 1
            result.issues.add("chunk_missing", chunk_id)
            continue
        if text_sha(chunk.text) != line["textSha256"]:
            result.counts["text_changed"] += 1
            result.issues.add("text_changed", chunk_id)
            continue
        want, have = normalized(line["layoutStart"]), normalized(chunk.layout_start)
        if want == have:
            result.counts["unchanged"] += 1
            continue
        action = "set" if want is not None else "clear"
        result.counts[action] += 1
        result.actions.append((chunk_id, action, want))
    for chunk in chunks:
        if chunk.id not in planned_ids and chunk.layout_start is not None:
            result.counts["unplanned_anchor"] += 1
            result.issues.add("unplanned_anchor", chunk.id)
    return result


async def apply_plan(anchors: AnchorStore, plan: DocumentPlan, concurrency: int) -> Counter:
    """Write the plan's ``set``/``clear`` actions and read them back."""
    outcome: Counter = Counter()
    semaphore = asyncio.Semaphore(concurrency)

    async def write(chunk_id: UUID, value: dict[str, Any] | None) -> bool:
        async with semaphore:
            try:
                await anchors.write(chunk_id, value)
                return True
            except Exception as e:  # reported per chunk; the other writes go on (best effort)
                plan.issues.add("write_failed", f"{chunk_id}:{type(e).__name__}")
                return False

    done = await asyncio.gather(*(write(chunk_id, value) for chunk_id, _, value in plan.actions))
    written = [(chunk_id, value) for (chunk_id, _, value), ok in zip(plan.actions, done) if ok]
    outcome["write_failed"] = len(plan.actions) - len(written)
    try:
        back = await anchors.read_back([chunk_id for chunk_id, _ in written])
    except Exception as e:
        plan.issues.add("read_back_failed", type(e).__name__)
        outcome["not_read_back"] = len(written)
        return outcome
    for chunk_id, value in written:
        if chunk_id in back and normalized(back[chunk_id]) == value:
            outcome["written"] += 1
        else:
            outcome["not_read_back"] += 1
            plan.issues.add("not_read_back", chunk_id)
    return outcome
