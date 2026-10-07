"""Write helpers shared by Weaviate repositories: failure records and cascading deletes."""
import asyncio
import logging
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.exceptions import WeaviateTimeoutError

import semant_demo.schemas as schemas
from semant_demo.schema.outcomes import StepFailure

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


class NoProgressError(RuntimeError):
    """A delete loop found objects it had already processed, so their writes did not take effect."""


def step_failure(step: str, item_id, exc: Exception) -> StepFailure:
    """Failure record for one write. Details stay in the log, not in the response."""
    logger.warning("Write step %s failed for %s: %s", step, item_id, exc)
    return StepFailure(
        item_id=str(item_id) if item_id is not None else None,
        step=step,
        message=f"{type(exc).__name__}: storage write failed",
        uncertain=isinstance(exc, (WeaviateTimeoutError, asyncio.TimeoutError, TimeoutError)),
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


async def _drain(collection, filters, process) -> None:
    """Apply ``process`` to every object matching ``filters`` until none match.

    ``process`` must make the object stop matching (delete it or its reference), so the
    first page is read again after each round. Stops with ``NoProgressError`` otherwise.
    """
    seen: set = set()
    while True:
        response = await collection.query.fetch_objects(filters=filters, limit=PAGE_SIZE, return_properties=[])
        if not response.objects:
            return
        guard_progress(seen, [o.uuid for o in response.objects])
        for obj in response.objects:
            await process(obj.uuid)
        if len(response.objects) < PAGE_SIZE:
            return


async def delete_references_to(collection, from_property: str, target_id: UUID) -> None:
    """Remove the ``from_property`` reference to ``target_id`` from every object holding it."""
    async def unlink(uuid):
        await collection.data.reference_delete(from_uuid=uuid, from_property=from_property, to=target_id)
    await _drain(collection, Filter.by_ref(from_property).by_id().equal(target_id), unlink)


async def delete_tag_cascade(client: WeaviateAsyncClient, names: schemas.CollectionNames, tag_id: UUID) -> None:
    """Delete a tag after its chunk tag references and its spans.

    Best effort without rollback: a failure stops the cascade and keeps what was done.
    """
    logger.info("Performing cascade deletion of tag %s", tag_id)
    chunks = client.collections.get(names.chunks_collection_name)
    for prop in ("automaticTag", "positiveTag", "negativeTag"):
        await delete_references_to(chunks, prop, tag_id)

    spans = client.collections.get(names.span_collection_name)
    await _drain(spans, Filter.by_ref("tag").by_id().equal(tag_id), spans.data.delete_by_id)

    await client.collections.get(names.tag_collection_name).data.delete_by_id(tag_id)


async def delete_collection_cascade(client: WeaviateAsyncClient, names: schemas.CollectionNames,
                                    collection_id: UUID) -> None:
    """Delete a collection after its chunk/document links and its tags (with their spans).

    Best effort without rollback: a failure stops the cascade and keeps what was done.
    """
    logger.info("Performing cascade deletion of user collection %s", collection_id)
    await delete_references_to(client.collections.get(names.chunks_collection_name),
                               names.user_collection_link_name, collection_id)
    await delete_references_to(client.collections.get(names.document_collection_name), "collection", collection_id)

    async def delete_tag(tag_id):
        await delete_tag_cascade(client, names, tag_id)
    await _drain(client.collections.get(names.tag_collection_name),
                 Filter.by_ref("userCollection").by_id().equal(collection_id), delete_tag)

    await client.collections.get(names.user_collection_name).data.delete_by_id(collection_id)
