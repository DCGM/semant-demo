import logging
from time import time
import weaviate
import weaviate.collections.classes.internal
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding, get_hyde_document_embedding
from weaviate.classes.query import QueryReference
from semant_demo.config import config

import logging

from weaviate.collections.classes.grpc import QueryReference
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateTimeoutError,
    WeaviateQueryError,
    WeaviateInvalidInputError,
    UnexpectedStatusCodeError,
    ResponseCannotBeDecodedError,
    WeaviateClosedClientError,
    InsufficientPermissionsError,
)
from semant_demo.weaviate_exceptions import WeaviateConnectError, WeaviateDataValidationError, WeaviateLimitError, WeaviateServerError, WeaviateOperationError 

import uuid

from semant_demo.weaviate_utils.tag_repository import TagRepository
from semant_demo.weaviate_utils.document_repository import DocumentRepository
from semant_demo.weaviate_utils.span_repository import SpanRepository
from semant_demo.weaviate_utils.text_chunk_repository import TextChunkRepository
from semant_demo.weaviate_utils.user_collection_repository import UserCollectionRepository

class WeaviateAbstraction():
    """
    Legacy composition root: owns the shared Weaviate client and bundles all
    repositories together for code that needs several of them in one call
    (e.g. semant_demo/rag/, semant_demo/tagging/tagging_utils.py).

    Routes/callers that only need a single repository should get it via that
    repository's own FastAPI dependency instead (e.g.
    routes.dependencies.get_document_repository), which reuses this same
    client under the hood. As each domain gains its own dependency, its
    direct use of this class should shrink and eventually disappear.
    """

    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

        # prepare instances of each weaviate table
        self.document = DocumentRepository(client=client, collectionNames=collectionNames)
        self.span = SpanRepository(client=client, collectionNames=collectionNames)
        self.tag = TagRepository(client=client, collectionNames=collectionNames)
        self.textChunk = TextChunkRepository(client=client, collectionNames=collectionNames)
        self.userCollection = UserCollectionRepository(client=client, collectionNames=collectionNames)

    @classmethod
    async def create(cls, config:Config) -> "WeaviateAbstraction":
        # Instantiate async client with custom params
        async_client = weaviate.use_async_with_custom(
            http_host=config.WEAVIATE_HOST, http_port=config.WEAVIATE_REST_PORT, http_secure=False,
            grpc_host=config.WEAVIATE_HOST, grpc_port=config.WEAVIATE_GRPC_PORT, grpc_secure=False,
        )
        # Connect and verify readiness
        await async_client.connect()  # :contentReference[oaicite:0]{index=0}
        if not await async_client.is_ready():  # :contentReference[oaicite:1]{index=1}
            logging.error("Weaviate is not ready.")
            await async_client.close()
            exit(-1)
        return cls(async_client, config.collectionNames)

    async def close(self):
        await self.client.close()  # :contentReference[oaicite:2]{index=2}