from semant_demo.config import config
from semant_demo.weaviate_client import WeaviateClient
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
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
_weaviate_client = None

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
    global _searcher
    if _searcher is None:
        _searcher = await WeaviateAbstraction.create(config)
    return _searcher

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

async def get_weaviate_client() -> WeaviateClient:
    global _weaviate_client
    if _weaviate_client is None:
        _weaviate_client = await WeaviateClient.create(config)
    return _weaviate_client