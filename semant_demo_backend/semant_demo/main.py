from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import openai
from semant_demo import schemas
from semant_demo.config import config
import logging
from semant_demo.weaviate_search import WeaviateSearch
import asyncio
from semant_demo.tagging import tag_and_store
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
#from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON
from glob import glob  
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy import select, update, bindparam   
from typing import AsyncGenerator   
#import db
from sqlalchemy import exc

import logging  

from semant_demo.schemas import Task, TasksBase

import json

from semant_demo.weaviate_search import DBError

"""
if os.path.exists(config.SQL_DB_URL):
    os.remove(config.SQL_DB_URL)
    print("Deleted old database file")
"""

"""
from semant_demo.celery_tagging import tag_and_store
from celery.result import AsyncResult
"""

logging.basicConfig(level=logging.INFO)

global_engine = None
global_async_session_maker = None

# Dependency
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    global global_engine, global_async_session_maker
    if global_engine is None:
        global_engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        global_async_session_maker = async_sessionmaker(global_engine, autocommit=False, autoflush=False)
    async with global_async_session_maker() as session:
        yield session    

openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)

global_searcher = None
async def get_search() -> WeaviateSearch:
    global global_searcher
    if global_searcher is None:
        global_searcher = await WeaviateSearch.create(config)
    return global_searcher
app = FastAPI()

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.ALLOWED_ORIGIN],  # http://localhost:9000
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, searcher: WeaviateSearch = Depends(get_search)) -> schemas.SearchResponse:
    print("Searching", flush=True)
    response = await searcher.search(req)
    return response


@app.post("/api/summarize/{summary_type}", response_model=schemas.SummaryResponse)
async def summarize(search_response: schemas.SearchResponse, summary_type: str) -> schemas.SummaryResponse:
    # build your snippets with IDs
    snippets = [
        f"[doc{i+1}]" + res.text.replace('\\n', ' ')
        for i, res in enumerate(search_response.results)
    ]

    system_prompt = "\n".join([
        "You are a summarization assistant.",
        "You will be given text snippets, each labeled with a unique ID like [doc1], [doc2], … [doc15].",
        "You should produce a single, concise summary that covers all the key points relevant to a user search query.",
        "After every fact that you extract from a snippet, append the snippet’s ID in square brackets—for example: “The gene ABC is upregulated in tumor cells [doc3].”",
        "If multiple snippets support the same fact, list all their IDs separated by commas: “This approach improved accuracy by 12% [doc2, doc7, doc11].”",
        "Do not introduce any facts that are not in the snippets. Focus on information that is relevant to the user query.",
        "Write the summary clearly and concisely.",
        "Keep the summary under 200 words."
    ])

    user_prompt = "\n".join([
        f'The user query is: "{search_response.search_request.query}"',
        "Here are the retrieved text snippets:",
        *snippets,
        "",
        "Please summarize these contexts, tagging each statement with its source ID. Do not add any other text."
    ])

    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )
    except openai.OpenAIError as e:
        # turn any SDK error into a 502
        logging.error(e)
        raise HTTPException(status_code=502, detail=str(e))

    summary_text = resp.choices[0].message.content.strip()

    return schemas.SummaryResponse(
        summary=summary_text,
        time_spent=search_response.time_spent,
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

@app.post("/api/tag", response_model=schemas.TagStartResponse)
async def start_tagging(tagReq: schemas.TagReqTemplate, background_tasks: BackgroundTasks, tagger: WeaviateSearch = Depends(get_search), session: AsyncSession = Depends(get_async_session)) -> schemas.TagStartResponse:
    print("Tagging...")
    print(tagReq)
    taskId = str(uuid.uuid4()) # generate id for current task
    try:
        try:
            async with session.begin():
                session.add(Task(taskId=taskId))
                await session.commit()
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed adding object to database. Task ID={taskId}')
            raise DBError(f'Failed adding new task object to database. Task ID={taskId}') from e

        background_tasks.add_task(tag_and_store, tagReq, taskId, tagger, global_async_session_maker)
        return {"job_started": True, "task_id": taskId, "message": "Tagging task started in the background"}
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail=str(e))
"""
    try:
        async with db.begin():
            stm = (delete(table).where(table.id == id))
            await db.execute(stm)
    except exc.SQLAlchemyError as e:
        logging.exception(f'Failed deleting object in database. Object probably does not exist. ID={id}')
        raise DBError(f'Failed deleting object in database. Object probably does not exist. ID={id}') from e
"""

@app.get("/api/tag/status/{taskId}")
async def check_status(taskId: str, session: AsyncSession = Depends(get_async_session)):
        try:
            task = await session.get(Task, taskId)
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed loading object from database. Task ID={taskId}')
            raise DBError(f'Failed loading object from database. Task ID={taskId}') from e
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        # prepare the result
        result = task.result
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = None

        logging.info(f"Repsonse status: {task.status}")

        return {"taskId": taskId, "status": task.status, "result": task.result, "all_texts_count": task.all_texts_count, "processed_count": task.processed_count}

@app.get("/api/get_tags", response_model=schemas.GetTagsResponse)
async def get_tags(tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetTagsResponse:
    response = await tagger.get_all_tags()
    return {"tags_lst": response}

@app.post("/api/tagged_texts", response_model=schemas.GetTagsResponse)
async def get_tags(tagger: WeaviateSearch = Depends(get_search)) -> schemas.GetTagsResponse:
    response = await tagger.get_all_tags()
    return {"tags_lst": response}