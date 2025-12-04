import openai
import langchain_google_genai 

from fastapi import FastAPI, Depends, HTTPException
import logging

from semant_demo import schemas
from semant_demo.config import config
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.rag.rag_factory import get_all_rag_configurations, RAG_INSTANCES, rag_factory
from time import time
from fastapi.staticfiles import StaticFiles
import os

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from semant_demo.routes import export_router

from semant_demo import schemas
from semant_demo.config import config
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.tagging.tagging_task import tag_and_store

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import Column, String, JSON
from glob import glob
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import select, update, bindparam, asc
from sqlalchemy import exc
from datetime import timezone

from typing import AsyncGenerator

from semant_demo.schemas import Task, TasksBase
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
global_summarizer = None
global_rag = None

async def get_search() -> WeaviateSearch:
    global global_searcher
    if global_searcher is None:
        global_searcher = await WeaviateSearch.create(config)
    return global_searcher


async def get_summarizer() -> TemplatedSearchResultsSummarizer:
    global global_summarizer
    if global_summarizer is None:
        global_summarizer = TemplatedSearchResultsSummarizer.create(config.SEARCH_SUMMARIZER_CONFIG)
    return global_summarizer

app = FastAPI()
# mount routes
app.include_router(export_router)

# Create tables on startup
@app.on_event("startup")
async def startup():
    global global_engine, global_async_session_maker
    global_engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
    global_async_session_maker = async_sessionmaker(global_engine, autocommit=False, autoflush=False)
    async with global_engine.begin() as conn:
        # drop all tables first
        #await conn.run_sync(TasksBase.metadata.drop_all)
        # create tables
        await conn.run_sync(TasksBase.metadata.create_all)
        
    #load rags configurations and create instances
    global global_searcher
    global_searcher = await get_search()
    rag_factory(global_config=config, configs_path=config.RAG_CONFIGS_PATH, searcher=global_searcher)
    

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.ALLOWED_ORIGIN],  # http://localhost:9000
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, searcher: WeaviateSearch = Depends(get_search),
                 summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer)) -> schemas.SearchResponse:
    start_time = time()

    response = await searcher.search(req)
    await summarizer(req, response)

    response.time_spent = time() - start_time
    return response


@app.post("/api/summarize/{summary_type}", response_model=schemas.SummaryResponse)
async def summarize(search_response: schemas.SearchResponse, summary_type: str, summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer)) -> schemas.SummaryResponse:
    start_time = time()
    if summary_type != "results":
        # only "results" is supported now
        raise HTTPException(status_code=400, detail=f"Unknown summary type: {summary_type}")

    summary = await summarizer.gen_results_summary(
        search_response.search_request.query,
        search_response.results,
    )
    time_spent = time() - start_time
    return schemas.SummaryResponse(
        summary=summary,
        time_spent=time_spent,
    )


@app.post("/api/question/{question_text}", response_model=schemas.SummaryResponse)
async def question(search_response: schemas.SearchResponse, question_text: str) -> schemas.SummaryResponse:
    # build your snippets with IDs
    snippets = [
        f"[doc{i+1}]" + res.text.replace('\\n', ' ')
        for i, res in enumerate(search_response.results)
    ]

    system_prompt = "\n".join([
        "You are a summarization assistant.",
        "You will be given text snippets, each labeled with a unique ID like [doc1], [doc2], … [doc15].",
        "When answering, rely only on the information in the snippets. Do not include any information that is not in the snippets.",
        "Any information you provide must be supported by the snippets and the snipet labels must be included as much as possible."
    ])

    user_prompt = "\n".join([
        "Here are the text snippets I want to talk about:",
        *snippets,
    ])

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
        {"role": "user", "content": question_text},
    ]
    print(messages)

    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
            temperature=0.0,
            max_tokens=300,
        )
    except openai.OpenAIError as e:
        logging.error(e)
        raise HTTPException(status_code=502, detail=str(e))

    summary_text = resp.choices[0].message.content.strip()

    return schemas.SummaryResponse(
        summary=summary_text,
        time_spent=search_response.time_spent,
    )

@app.get("/api/rag/configurations", response_model=list[schemas.RagRouteConfig])
async def get_avalaible_rag_configurations():
    return get_all_rag_configurations()

@app.post("/api/rag", response_model=schemas.RagResponse)
async def rag(request: schemas.RagRequestMain) -> schemas.RagResponse:
    #find and check rag
    id = request.rag_id
    if id not in RAG_INSTANCES:
        raise HTTPException(status_code=400, detail=f"Unknown RAG configuration: {id}.")
    
    #load class and call instance
    rag_instance = RAG_INSTANCES[id]
    return await rag_instance.rag_request(request=request.rag_request)
    

if os.path.isdir(config.STATIC_PATH):
    logging.info(f"Serving static files from '{config.STATIC_PATH}' directory")
    app.mount("/", StaticFiles(directory=config.STATIC_PATH,
              html=True), name="static")
else:
    logging.warning(
        f"'{config.STATIC_PATH}' directory not found. Static files will not be served.")
