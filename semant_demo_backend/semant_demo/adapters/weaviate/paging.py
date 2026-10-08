"""Reading every object matching a filter, page by page."""
from typing import Any

PAGE_SIZE = 100


async def fetch_all(collection, *, filters=None, page_size: int = PAGE_SIZE, **fetch_kwargs: Any) -> list:
    """All objects of ``collection`` matching ``filters``, read with offset paging.

    The full list is read before returning, so callers that write to the returned objects
    afterwards cannot change the pages being read. ``fetch_kwargs`` (``sort``,
    ``return_properties``, ``return_references``, ...) are passed to ``fetch_objects``.
    Weaviate limits ``offset + limit`` to ``QUERY_MAXIMUM_RESULTS`` (10 000 by default);
    a larger result fails instead of being truncated silently.
    """
    objects: list = []
    while True:
        response = await collection.query.fetch_objects(
            filters=filters, limit=page_size, offset=len(objects), **fetch_kwargs)
        objects.extend(response.objects)
        if len(response.objects) < page_size:
            return objects
