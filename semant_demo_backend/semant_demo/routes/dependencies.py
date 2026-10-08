from fastapi import HTTPException
from starlette.requests import HTTPConnection

from semant_demo.adapters.sql.users import UserLookup
from semant_demo.adapters.llm.responses import ResponsesChat
from semant_demo.adapters.topicer.client import TopicerClient
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.bootstrap import AppResources, WeaviateRepositories
from semant_demo.config import Config
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.search.service import SearchBackends
from semant_demo.rag.rag_factory import RagRegistry

from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator

#summarizer
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer


def get_resources(connection: HTTPConnection) -> AppResources:
    # Resources exist only while the application lifespan is running.
    resources = getattr(connection.app.state, "resources", None)
    if resources is None:
        raise HTTPException(status_code=503, detail="Application is not started.")
    return resources

def get_config(connection: HTTPConnection) -> Config:
    return connection.app.state.config

async def get_async_session(connection: HTTPConnection) -> AsyncGenerator[AsyncSession, None]:
    async with get_resources(connection).session_maker() as session:
        yield session

async def get_user_lookup(connection: HTTPConnection) -> AsyncGenerator[UserLookup, None]:
    async with get_resources(connection).session_maker() as session:
        yield UserLookup(session)

def _weaviate(connection: HTTPConnection) -> WeaviateRepositories:
    # Connected at startup (bootstrap); never opened from a request.
    weaviate = get_resources(connection).weaviate
    if weaviate is None:
        raise HTTPException(status_code=503, detail="Application is not started.")
    return weaviate

async def get_documents(connection: HTTPConnection) -> DocumentRepository:
    return _weaviate(connection).documents

async def get_tags(connection: HTTPConnection) -> TagRepository:
    return _weaviate(connection).tags

async def get_collections(connection: HTTPConnection) -> UserCollectionRepository:
    return _weaviate(connection).collections

async def get_annotation_store(connection: HTTPConnection) -> AnnotationStore:
    weaviate = _weaviate(connection)
    return AnnotationStore(collections=weaviate.collections, tags=weaviate.tags, spans=weaviate.spans,
                           chunk_tags=weaviate.chunk_tags, documents=weaviate.documents)

async def get_search_backends(connection: HTTPConnection) -> SearchBackends:
    weaviate = _weaviate(connection)
    return SearchBackends(chunks=weaviate.search, collections=weaviate.collections, tags=weaviate.tags,
                          embeddings=get_resources(connection).embeddings)

def get_topicer(connection: HTTPConnection) -> TopicerClient:
    return get_resources(connection).topicer

def get_span_chat(connection: HTTPConnection) -> ResponsesChat:
    return get_resources(connection).span_chat

async def get_summarizer(connection: HTTPConnection) -> TemplatedSearchResultsSummarizer:
    return get_resources(connection).get_summarizer()

def get_rag_registry(connection: HTTPConnection) -> RagRegistry:
    return get_resources(connection).rag


def get_search_filters(connection: HTTPConnection):
    from semant_demo.features.search.filters import load_search_filters_config
    return load_search_filters_config(get_config(connection).SEARCH_FILTERS_CONFIG)
