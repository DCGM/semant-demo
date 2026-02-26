from fastapi import APIRouter
from semant_demo.config import config
from semant_demo.weaviate_search import WeaviateSearch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from typing import AsyncGenerator

global_engine = None
global_async_session_maker = None
global_searcher = None

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    global global_engine, global_async_session_maker
    if global_engine is None:
        global_engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        global_async_session_maker = async_sessionmaker(global_engine, autocommit=False, autoflush=True, expire_on_commit=False)
    async with global_async_session_maker() as session:
        yield session

async def get_search() -> WeaviateSearch:
    global global_searcher
    if global_searcher is None:
        global_searcher = await WeaviateSearch.create(config)
    return global_searcher