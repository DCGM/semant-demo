import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
# from semant_demo.rag.rag_generator import RagGenerator
import asyncio
#import aiofiles # load multiple files simultaneously

from semant_demo.tagging.tagging_utils import tag_and_store
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON
from glob import glob
from sqlalchemy import select, update, bindparam, asc
from typing import AsyncGenerator
# import db
from sqlalchemy import select, update, asc
# import db
from sqlalchemy import exc
from datetime import timezone

import logging

from semant_demo.schemas import Task, TasksBase

import json
import yaml

from semant_demo.tagging.sql_utils import DBError, update_task_status
from semant_demo.tagging.tagging_utils import getTaskByName

#import dependencies
from semant_demo.routes.dependencies import get_async_session, get_engine, get_search

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parents[1]
TAG_CONFIG_DIR = BASE_DIR / "tagging" / "configs"
# TAG_CONFIG_DIR = r"semant_demo_backend\semant_demo\tagging\configs"

exp_router = APIRouter()



# TagSpans
@exp_router.post("/api/tag_spans", response_model=schemas.TagSpanWriteResponse)
async def upsert_tag_spans(body: schemas.TagSpanCreateSeparateRequest, tagger: WeaviateAbstraction = Depends(get_search)) -> schemas.TagSpanWriteResponse:
    """
    Adds new TagSpan
    """
    await tagger.textChunk.tag(body.span.chunkId, body.span)
    return schemas.TagSpanWriteResponse(stored_in=[schemas.SpanStoreMode.separate])


@exp_router.get("/api/tag_spans/{chunk_id}", response_model=list[schemas.TagSpan])
async def read_tag_spans(
    chunk_id: str,
    tagger: WeaviateAbstraction = Depends(get_search)
) -> list[schemas.TagSpan]:
    """
    Get stored TagSpans for a given chunk ID.
    """
    return await tagger.span.read(chunk_id)


@exp_router.patch("/api/tag_spans/update", response_model=dict)
async def update_tag_span(
    body: schemas.TagSpanUpdateSeparateRequest,
    tagger: WeaviateAbstraction = Depends(get_search)
):
    """
    Update TagSpan's information (start, end, tagId, ...)
    """
    try:
        update_fields = body.tagSpan

        if not update_fields:
            raise HTTPException(
                status_code=400,
                detail="No fields provided for update"
            )

        await tagger.span.update(
            span_id=body.span_id,
            update_fields=update_fields
        )

        return {
            "status": "success",
            "updated_fields": update_fields
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@exp_router.delete("/api/tag_spans/{span_id}", response_model=dict)
async def delete_tag_span(
    span_id: str,
    tagger: WeaviateAbstraction = Depends(get_search)
):
    """
    Delete a TagSpan's information
    """
    try:
        logging.info(f"Deleting span with id: {span_id}")
        response = await tagger.textChunk.untag(span_id=span_id)
        logging.info(f"{response}")
        return {
            "status": "success" if response else "failure",
            "span_id": span_id
        }

    except Exception as e:
        logging.error(f"{e}")
        raise HTTPException(status_code=500, detail=str(e))

# /TagSpans
