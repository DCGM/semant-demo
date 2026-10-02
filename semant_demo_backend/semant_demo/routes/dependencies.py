from fastapi import Depends

from semant_demo.config import config
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
from semant_demo.weaviate_utils.document_repository import DocumentRepository
from semant_demo.weaviate_utils.tag_repository import TagRepository
from semant_demo.weaviate_utils.user_collection_repository import UserCollectionRepository
#from semant_demo.weaviate_tag import WeaviateSearchAndTag

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator

#summarizer
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer

_engine = None
_async_session_maker = None
_searcher = None
_tagger = None
_summarizer = None

def get_engine():
    global _engine, _async_session_maker
    if _engine is None:
        _engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        _async_session_maker = async_sessionmaker(_engine, autocommit=False, autoflush=True, expire_on_commit=False)
    return _engine, _async_session_maker

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    _, _async_session_maker = get_engine()
    async with _async_session_maker() as session:
        yield session

async def get_search() -> WeaviateAbstraction:
    """
    Legacy dependency: returns the shared bag of all Weaviate repositories.

    Still needed by code that touches several repositories in one call
    (e.g. semant_demo/rag/, semant_demo/tagging/tagging_utils.py). New
    routes that only need one repository should depend on that
    repository's dedicated provider instead (e.g. get_document_repository
    below), which reuses the same underlying client/connection.
    """
    global _searcher
    if _searcher is None:
        _searcher = await WeaviateAbstraction.create(config)
    return _searcher


async def get_document_repository(
    repositories: WeaviateAbstraction = Depends(get_search),
) -> DocumentRepository:
    return repositories.document

async def get_tag_repository(
    repositories: WeaviateAbstraction = Depends(get_search),
) -> TagRepository:
    return repositories.tag

async def get_user_collection_repository(
    repositories: WeaviateAbstraction = Depends(get_search),
) -> UserCollectionRepository:
    return repositories.userCollection

async def cleanup_dependencies():
    global _engine, _async_session_maker, _searcher
    if _searcher:
        await _searcher.close()
    if _engine:
        await _engine.dispose()

async def get_summarizer() -> TemplatedSearchResultsSummarizer:
    global _summarizer
    if _summarizer is None:
        _summarizer = TemplatedSearchResultsSummarizer.create(config.SEARCH_SUMMARIZER_CONFIG)
    return _summarizer


def get_search_filters():
    from semant_demo.search_filters import load_search_filters_config
    return load_search_filters_config(config.SEARCH_FILTERS_CONFIG)
