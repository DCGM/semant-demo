from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from weaviate import WeaviateAsyncClient

import semant_demo.schemas as schemas
from semant_demo.weaviate_utils.helpers import WeaviateHelpers


class WeaviateBaseRepository(ABC):
    """
    Base class for repositories that expose a CRUD-shaped API over one Weaviate collection.

    A subclass that does not support some operation (e.g. a read-only domain)
    should still implement the method, but raise NotImplementedError with an
    explanation - this keeps the CRUD surface discoverable and consistent
    across domains instead of silently omitting methods.
    """

    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    @abstractmethod
    async def create(self, *args: Any, **kwargs: Any) -> Any: ...

    @abstractmethod
    async def read(self, *args: Any, **kwargs: Any) -> Any: ...

    @abstractmethod
    async def read_all(self, *args: Any, **kwargs: Any) -> Any: ...

    @abstractmethod
    async def update(self, *args: Any, **kwargs: Any) -> Any: ...

    @abstractmethod
    async def delete(self, *args: Any, **kwargs: Any) -> Any: ...

    async def _paginate_objects(
        self,
        collection,
        filters=None,
        page_size: int = 100,
        **fetch_kwargs: Any,
    ) -> AsyncIterator[Any]:
        """
        Yields objects from a Weaviate collection page by page until exhausted.

        Args:
            collection: a Weaviate collection handle (from client.collections.get(...)).
            filters: optional weaviate.classes.query.Filter to apply.
            page_size: number of objects to fetch per page.
            **fetch_kwargs: forwarded to collection.query.fetch_objects (e.g. return_references).
        """
        offset = 0
        while True:
            response = await collection.query.fetch_objects(
                filters=filters,
                limit=page_size,
                offset=offset,
                **fetch_kwargs,
            )
            if not response.objects:
                return
            for obj in response.objects:
                yield obj
            if len(response.objects) < page_size:
                return
            offset += page_size
