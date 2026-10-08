"""Transitional bundle of all Weaviate repositories.

Only callers not migrated yet use it: AI assistance (#207) and span chat. Migrated
routes, search, RAG, annotations and the collection access checks depend on the
individual repositories in ``semant_demo.adapters.weaviate``.
Remove this class when the last of these callers has moved.
"""
from weaviate import WeaviateAsyncClient

from semant_demo import schemas
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository


class WeaviateAbstraction:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

        self.document = DocumentRepository(client, collectionNames)
        self.span = SpanRepository(client, collectionNames)
        self.tag = TagRepository(client, collectionNames)
        self.userCollection = UserCollectionRepository(client, collectionNames)
