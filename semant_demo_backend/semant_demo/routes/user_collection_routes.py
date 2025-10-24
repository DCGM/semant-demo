import os
import openai
import logging

from fastapi import APIRouter, Depends, HTTPException

from semant_demo import schemas
from semant_demo.config import config
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.rag_generator import RagGenerator
from time import time
import asyncio

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import openai
from semant_demo import schemas
from semant_demo.config import config
import logging
from semant_demo.weaviate_search import WeaviateSearch
import asyncio
from semant_demo.tagging.tagging_task import tag_and_store
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
#from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON
from glob import glob
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import select, update, bindparam, asc
from typing import AsyncGenerator
#import db
from sqlalchemy import exc
from datetime import timezone

import logging

from semant_demo.schemas import Task, TasksBase

import json

from semant_demo.tagging.sql_utils import DBError, update_task_status
from semant_demo.tagging.tagging_task import getTaskByName


logging.basicConfig(level=logging.INFO)

global_engine = None
global_async_session_maker = None

# Dependency
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    global global_engine, global_async_session_maker
    if global_engine is None:
        global_engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        global_async_session_maker = async_sessionmaker(global_engine, autocommit=False, autoflush=True, expire_on_commit=False)
    async with global_async_session_maker() as session:
        yield session

openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)

global_searcher = None

async def get_search() -> WeaviateSearch:
    global global_searcher
    if global_searcher is None:
        global_searcher = await WeaviateSearch.create(config)
    return global_searcher

exp_router = APIRouter()

@exp_router.post("/api/user_collection", response_model=schemas.CreateResponse)
async def create_user_collection(collectionReq: schemas.UserCollectionReqTemplate,
                                 tagger: WeaviateSearch = Depends(get_search),
                                 session: AsyncSession = Depends(get_async_session)) -> schemas.CreateResponse:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    try:
        collection_id = await tagger.add_collection(collectionReq)
        if collection_id is None:
            raise Exception("weaviate error")
        return {"created": True,
                "message": f"Collection {collectionReq.collection_name} created with collection id {collection_id}"}
    except Exception as e:
        logging.error(e)
        return {"created": False,
                "message": f"Collection {collectionReq.collection_name} not created becacause of: {e}"}


@exp_router.get("/api/collections", response_model=schemas.GetCollectionsResponse)
async def fetch_collections(userId: str,
                            tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetCollectionsResponse:
    """
    Retrieves all collections for given user
    """
    response = await tagger.fetch_all_collections(userId)
    return response


@exp_router.post("/api/chunk_2_collection", response_model=schemas.CreateResponse)
async def add_chunk_2_collection(req: schemas.Chunk2CollectionReq, tagger: WeaviateSearch = Depends(get_search),
                                 session: AsyncSession = Depends(get_async_session)) -> schemas.CreateResponse:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    try:
        err = await tagger.add_chunk_to_collection(req)
        if err:
            raise Exception("weaviate error")
        return {"created": True, "message": f"Chunk added to collection"}
    except Exception as e:
        logging.error(e)
        return {"created": False, "message": f"Chunk not added to collection becacause of: {e}"}


@exp_router.get("/api/chunks_of_collection", response_model=schemas.GetCollectionChunksResponse)
async def get_collection_chunks(collectionId: str,
                                tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetCollectionChunksResponse:
    """
    Returns chunks which belong to collection given by id
    """
    try:
        logging.info(f"In get collection chunks {collectionId}")
        response = await tagger.get_collection_chunks(collectionId)
        return response
    except Exception as e:
        logging.error(f"{e}")
