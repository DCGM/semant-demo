# Richard Juřica's version of API for handling user collections
import logging
from fastapi import APIRouter, Depends, HTTPException, Response, status
from uuid import UUID
from semant_demo.schemas import (
    GetTagsResponse,
)
from semant_demo.schema.collections import Collection, PostCollection, PatchCollection, CollectionStats
from semant_demo.routes.dependencies import get_weaviate_client
from semant_demo.weaviate_client import WeaviateClient

router = APIRouter()

@router.post("/api/v1/collections/{collection_id}/documents/{document_id}")
async def add_document_to_collection(
    collection_id: UUID,
    document_id: UUID,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> dict:
    success = await wv_client.add_document_to_collection(
        document_id=document_id,
        collection_id=collection_id,
    )
    return {
        "success": success,
        "message": "Document added to collection" if success else "Failed to add document to collection"
    }


@router.delete("/api/v1/collections/{collection_id}/documents/{document_id}")
async def remove_document_from_collection(
    collection_id: UUID,
    document_id: UUID,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> dict:
    success = await wv_client.remove_document_from_collection(
        document_id=document_id,
        collection_id=collection_id,
    )
    return {
        "success": success,
        "message": "Document removed from collection" if success else "Failed to remove document from collection"
    }
