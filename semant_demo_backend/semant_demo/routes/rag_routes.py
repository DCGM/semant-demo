

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

#import dependencies
from semant_demo.routes.dependencies import get_async_session, get_search #, get_engine


from semant_demo.rag.rag_factory import get_all_rag_configurations, RAG_INSTANCES

import datetime
import logging

exp_router = APIRouter()

#routest
@exp_router.get("/api/rag/configurations", response_model=list[schemas.RagRouteConfig])
async def get_avalaible_rag_configurations():
    return get_all_rag_configurations()

@exp_router.post("/api/rag", response_model=schemas.RagResponse)
async def rag(request: schemas.RagRequestMain, searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.RagResponse:
    #find and check rag
    id = request.rag_id
    if id not in RAG_INSTANCES:
        raise HTTPException(status_code=400, detail=f"Unknown RAG configuration: {id}.")
    
    #load class and call instance
    rag_instance = RAG_INSTANCES[id]
    return await rag_instance.rag_request(request=request.rag_request, searcher=searcher)

@exp_router.post("/api/rag/explain")
async def explain_selection(request : schemas.ExplainRequest):
    id = request.rag_id
    if id not in RAG_INSTANCES:
        raise HTTPException(status_code=400, detail=f"Unknown RAG configuration: {id} used for explaining.")
    
    #load class and call instance
    rag_instance = RAG_INSTANCES[id]
    return await rag_instance.explain_selection(request=request)

# endpoint of feedback - like/dislike
@exp_router.post("/api/rag/feedback")
async def save_feedback(request : schemas.FeedbackRequest, db: AsyncSession = Depends(get_async_session)):
    try:
        selser = select(schemas.RagUserFeedback).where(schemas.RagUserFeedback.response_id == request.response_id)
        result = await db.execute(selser)
        ex_feedback = result.scalar_one_or_none()

        if (ex_feedback):   #update
            ex_feedback.rating = request.rating
            ex_feedback.comment = request.comment
            ex_feedback.error_types = ",".join(request.error_types) if request.rating == -1 else None
            ex_feedback.timestamp = datetime.datetime.now(datetime.timezone.utc)
        else:               #create new 
            serialized_sources = [doc.model_dump(mode='json') for doc in request.sources] if request.sources else []
            new_feedback = schemas.RagUserFeedback(
                response_id=request.response_id,
                rag_id=request.rag_id,
                question=request.question,
                answer=request.answer,
                rating=request.rating,
                error_types= ",".join(request.error_types) if request.rating == -1 else None,
                comment=request.comment,
                sources=serialized_sources
            )
            db.add(new_feedback)
        
        await db.commit()

        return {"status" : "success"}

    except Exception as e:
        await db.rollback()
        logging.error(f"Feedback error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error.")

    