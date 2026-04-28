import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response

from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
# from semant_demo.rag.rag_generator import RagGenerator
import asyncio
# import aiofiles # load multiple files simultaneously

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

# import dependencies
from semant_demo.routes.dependencies import get_async_session, get_engine, get_search
from semant_demo.schema.spans import (
    PostSpan,
    PatchSpan,
    DeleteSpansForTagsRequest,
    DeleteSpansForTagsResponse,
    BulkUpdateSpansRequest,
    BulkUpdateSpansResponse,
)
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parents[1]
TAG_CONFIG_DIR = BASE_DIR / "tagging" / "configs"
# TAG_CONFIG_DIR = r"semant_demo_backend\semant_demo\tagging\configs"

exp_router = APIRouter()


# TagSpans
@exp_router.post("/api/tag_spans", response_model=schemas.TagSpan)
async def create_tag_span(span: PostSpan, tagger: WeaviateAbstraction = Depends(get_search)) -> schemas.TagSpan:
    """
    Adds new TagSpan
    """
    return await tagger.span.create(span=span)


@exp_router.get("/api/tag_spans", response_model=list[schemas.TagSpan])
async def read_tag_spans(
    chunk_id: str | None = Query(
        default=None, description="Filter spans by chunk ID"),
    collection_id: str | None = Query(
        default=None, description="Filter spans by collection ID"),
    tagger: WeaviateAbstraction = Depends(get_search)
) -> list[schemas.TagSpan]:
    """
    Get stored TagSpans for a given chunk ID and collection ID.
    """
    return await tagger.span.read_all(chunk_id=chunk_id, collection_id=collection_id)


@exp_router.post("/api/tag_spans/batch", response_model=dict[str, list[schemas.TagSpan]])
async def read_tag_spans_batch(
    body: schemas.TagSpanBatchRequest,
    tagger: WeaviateAbstraction = Depends(get_search)
) -> dict[str, list[schemas.TagSpan]]:
    """
    Get stored TagSpans for multiple chunk IDs in a single request.
    """
    return await tagger.span.read_batch(chunk_ids=body.chunk_ids, collection_id=body.collection_id)


@exp_router.patch("/api/tag_spans/{span_id}", response_model=schemas.TagSpan)
async def update_tag_span(
    span_id: str,
    body: PatchSpan,
    tagger: WeaviateAbstraction = Depends(get_search)
):
    """
    Update TagSpan's information (start, end, tagId, ...)
    """

    return await tagger.span.update(
        span_id=span_id,
        update_fields=body
    )


@exp_router.post(
    "/api/tag_spans/bulk_update",
    response_model=BulkUpdateSpansResponse,
)
async def bulk_update_tag_spans(
    body: BulkUpdateSpansRequest,
    tagger: WeaviateAbstraction = Depends(get_search),
) -> BulkUpdateSpansResponse:
    """
    Apply the same :class:`PatchSpan` to many spans in one round-trip.

    Used by the AI-assist "Approve / Reject all selected" action — collapses
    N PATCH calls into one and lets the server fan them out concurrently.
    """
    spans = await tagger.span.bulk_update(
        span_ids=body.span_ids,
        update_fields=body.update,
    )
    return BulkUpdateSpansResponse(spans=spans)


@exp_router.delete("/api/tag_spans/{span_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag_span(
    span_id: str,
    tagger: WeaviateAbstraction = Depends(get_search)
):
    """
    Delete a TagSpan's information
    """
    await tagger.span.delete(span_id=span_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@exp_router.post(
    "/api/tag_spans/in_document/delete",
    response_model=DeleteSpansForTagsResponse,
)
async def delete_spans_for_tags_in_document(
    body: DeleteSpansForTagsRequest,
    tagger: WeaviateAbstraction = Depends(get_search),
) -> DeleteSpansForTagsResponse:
    """
    Bulk-delete approved (``type == 'pos'``) spans for the given tag ids
    within a single (collection, document) scope. Negatives and unresolved
    auto suggestions are left untouched.
    """
    deleted = await tagger.span.delete_all_spans_for_tags_in_document(
        collection_id=body.collection_id,
        document_id=body.document_id,
        tag_ids=body.tag_ids,
    )
    return DeleteSpansForTagsResponse(deleted=deleted)

# /TagSpans
