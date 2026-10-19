"""Write helpers shared by Weaviate repositories: failure records and cascading deletes."""
import asyncio
import logging
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.core.errors import IncompleteWriteError
from semant_demo.core.outcomes import StepFailure

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


class NoProgressError(RuntimeError):
    """A delete loop found objects it had already processed, so their writes did not take effect."""


def step_failure(step: str, item_id, exc: Exception) -> StepFailure:
    """Failure record for one write. The log and the response name only the exception class."""
    logger.warning("Write step %s failed for %s: %s", step, item_id, type(exc).__name__)
    return StepFailure(
        item_id=str(item_id) if item_id is not None else None,
        step=step,
        message=f"{type(exc).__name__}: storage write failed",
        uncertain=_is_timeout(exc),
    )


def guard_progress(seen: set, page_ids) -> None:
    """Stop a "process the first page again" loop once a page repeats processed objects.

    Such loops rely on each processed object leaving the filter. If one is returned
    again, its write did not take effect, and looping would never terminate.
    """
    page_ids = [str(i) for i in page_ids]
    repeated = [i for i in page_ids if i in seen]
    if repeated:
        raise NoProgressError(
            f"{len(repeated)} object(s) still match after being processed; stopping to avoid an endless loop"
        )
    seen.update(page_ids)


class _Progress:
    """Completed steps of a cascade, so a failure can say what was already done."""

    def __init__(self) -> None:
        self.step = ""
        self.completed: dict[str, int] = {}

    def at(self, step: str) -> None:
        self.step = step

    def done(self) -> None:
        self.completed[self.step] = self.completed.get(self.step, 0) + 1


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, (WeaviateTimeoutError, asyncio.TimeoutError, TimeoutError))


async def _drain(collection, filters, process, progress: _Progress, step: str) -> None:
    """Apply ``process`` to every object matching ``filters`` until none match.

    ``process`` must make the object stop matching (delete it or its reference), so the
    first page is read again after each round, also after a short page, and only an
    empty result ends the loop. Stops with ``NoProgressError`` when a processed object
    still matches (a write that reported success without taking effect).
    """
    seen: set = set()
    while True:
        progress.at(step)
        response = await collection.query.fetch_objects(filters=filters, limit=PAGE_SIZE, return_properties=[])
        if not response.objects:
            return
        guard_progress(seen, [o.uuid for o in response.objects])
        for obj in response.objects:
            await process(obj.uuid)
            progress.at(step)
            progress.done()


async def _delete_references_to(collection, from_property: str, target_id: UUID, progress: _Progress,
                                step: str) -> None:
    """Remove the ``from_property`` reference to ``target_id`` from every object holding it."""
    async def unlink(uuid):
        await collection.data.reference_delete(from_uuid=uuid, from_property=from_property, to=target_id)
    await _drain(collection, Filter.by_ref(from_property).by_id().equal(target_id), unlink, progress, step)


async def _tag_cascade(client: WeaviateAsyncClient, names: CollectionNames, spans, tag_id: UUID,
                       collection_id: UUID | None, progress: _Progress) -> None:
    """Unlink the tag from chunks, delete its spans (in ``collection_id``'s tenant; skipped
    when ``None``: the tenant was removed already), then the tag."""
    chunks = client.collections.get(names.chunks_collection_name)
    for prop in ("automaticTag", "positiveTag", "negativeTag"):
        await _delete_references_to(chunks, prop, tag_id, progress, "unlink_chunk_tag")

    if collection_id is not None:
        progress.at("delete_span")
        deleted = await spans.delete_by_tag(collection_id, tag_id)
        progress.completed["delete_span"] = progress.completed.get("delete_span", 0) + deleted

    progress.at("delete_tag")
    await client.collections.get(names.tag_collection_name).data.delete_by_id(tag_id)
    progress.done()


def _incomplete(what: str, progress: _Progress, exc: Exception) -> IncompleteWriteError:
    logger.warning("Deleting %s stopped at step %s after %s: %s", what, progress.step, progress.completed,
                   type(exc).__name__)
    done = ", ".join(f"{n} x {step}" for step, n in progress.completed.items()) or "nothing"
    cause = ("a deletion reported success without taking effect" if isinstance(exc, NoProgressError)
             else f"{type(exc).__name__}: storage write failed")
    return IncompleteWriteError(
        f"Deleting the {what} stopped at step {progress.step} ({cause}). Completed before: {done}. "
        f"Completed deletions are kept; deleting the {what} again continues where it stopped.",
        step=progress.step, completed=progress.completed, uncertain=_is_timeout(exc))


async def delete_tag_cascade(client: WeaviateAsyncClient, names: CollectionNames, spans, tag_id: UUID,
                             collection_id: UUID | None) -> None:
    """Delete a tag after its chunk tag references and its spans (``spans``: the
    ``SpanRepository``; ``collection_id``: the tag's collection, whose tenant holds them;
    ``None`` for a tag of no single collection, which has no spans).

    Best effort without rollback: a failure stops the cascade, keeps what was done and
    raises ``IncompleteWriteError`` naming the failed step and the completed steps
    (``unlink_chunk_tag``, ``delete_span``, ``delete_tag``). Repeating the deletion is
    safe and continues with what is left.
    """
    logger.info("Performing cascade deletion of tag %s", tag_id)
    progress = _Progress()
    try:
        await _tag_cascade(client, names, spans, tag_id, collection_id, progress)
    except Exception as exc:
        raise _incomplete("tag", progress, exc) from exc


async def delete_collection_cascade(client: WeaviateAsyncClient, names: CollectionNames, spans,
                                    collection_id: UUID) -> None:
    """Delete a collection after its chunk/document links, its tags and its annotation
    tenant (with all its spans).

    Best effort without rollback: a failure stops the cascade, keeps what was done and
    raises ``IncompleteWriteError`` (steps ``unlink_chunk``, ``unlink_document``, the tag
    steps for each tag, ``delete_annotation_tenant``, ``delete_collection``). The tenant
    counts as removed only when a lookup afterwards no longer finds it. Repeating the
    deletion is safe and continues with what is left.
    """
    logger.info("Performing cascade deletion of user collection %s", collection_id)
    progress = _Progress()
    try:
        await _delete_references_to(client.collections.get(names.chunks_collection_name),
                                    names.user_collection_link_name, collection_id, progress, "unlink_chunk")
        await _delete_references_to(client.collections.get(names.document_collection_name), "collection",
                                    collection_id, progress, "unlink_document")

        tags = client.collections.get(names.tag_collection_name)
        seen: set = set()
        while True:
            progress.at("delete_tag")
            response = await tags.query.fetch_objects(
                filters=Filter.by_ref("userCollection").by_id().equal(collection_id),
                limit=PAGE_SIZE, return_properties=[])
            if not response.objects:
                break
            guard_progress(seen, [o.uuid for o in response.objects])
            for obj in response.objects:
                # The tenant removal below deletes the spans of all tags at once.
                await _tag_cascade(client, names, spans, obj.uuid, None, progress)

        progress.at("delete_annotation_tenant")
        await spans.remove_tenant(collection_id)
        progress.done()

        progress.at("delete_collection")
        await client.collections.get(names.user_collection_name).data.delete_by_id(collection_id)
        progress.done()
    except Exception as exc:
        raise _incomplete("collection", progress, exc) from exc
