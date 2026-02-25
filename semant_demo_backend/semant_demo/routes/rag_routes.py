

from fastapi import APIRouter, Depends, HTTPException

from semant_demo.config import config
from semant_demo import schemas
from semant_demo.weaviate_search import WeaviateSearch

from semant_demo.rag.rag_factory import get_all_rag_configurations, RAG_INSTANCES

import datetime
import json
#dependency
global_searcher = None

async def get_search() -> WeaviateSearch:
    global global_searcher
    if global_searcher is None:
        global_searcher = await WeaviateSearch.create(config)
    return global_searcher

exp_router = APIRouter()

#routest
@exp_router.get("/api/rag/configurations", response_model=list[schemas.RagRouteConfig])
async def get_avalaible_rag_configurations():
    return get_all_rag_configurations()

@exp_router.post("/api/rag", response_model=schemas.RagResponse)
async def rag(request: schemas.RagRequestMain, searcher: WeaviateSearch = Depends(get_search)) -> schemas.RagResponse:
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
async def save_feedback(request : schemas.FeedbackRequest):
    feedback_data = request.model_dump(mode="json")
    feedback_data["timestamp"] = datetime.datetime.now().isoformat()

    with open("user_feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(feedback_data, ensure_ascii=False) + "\n")

    return {"status" : "success"}