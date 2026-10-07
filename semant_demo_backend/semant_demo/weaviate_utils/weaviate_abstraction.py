"""Transitional bundle of all Weaviate repositories.

Only callers not migrated yet use it: span routes and AI assistance (#206/#207), span
chat, search, summarizer and RAG (#205). Migrated routes and the collection access
checks depend on the individual repositories in ``semant_demo.adapters.weaviate``.
Remove this class when the last of these callers has moved.
"""
from weaviate import WeaviateAsyncClient

from semant_demo import schemas
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.config import Config
from semant_demo.weaviate_utils.span import Span
from semant_demo.weaviate_utils.text_chunk import TextChunk


class WeaviateAbstraction:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

        self.document = DocumentRepository(client, collectionNames)
        self.span = Span(client=client, collectionNames=collectionNames)
        self.tag = TagRepository(client, collectionNames)
        self.textChunk = TextChunk(client=client, collectionNames=collectionNames)
        self.userCollection = UserCollectionRepository(client, collectionNames)

    @classmethod
    async def create(cls, config: Config) -> "WeaviateAbstraction":
        """Own connection for standalone scripts. The application gets its client from bootstrap."""
        return cls(await connect_weaviate(config), config.collectionNames)

    async def close(self):
        await self.client.close()
