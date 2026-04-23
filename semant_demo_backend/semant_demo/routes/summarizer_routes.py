
import openai
import time
import os

from fastapi import APIRouter, Depends, HTTPException
from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
from semant_demo.config import config
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer

#import dependencies
from semant_demo.routes.dependencies import get_search, get_summarizer #, get_engine
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User
import logging


exp_router = APIRouter()


openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
@exp_router.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, searcher: WeaviateAbstraction = Depends(get_search),
                 summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                 current_user: User | None = Depends(current_active_optional_user)) -> schemas.SearchResponse:
    start_time = time.time()

    # <authorization>
    if req.user_collection_id is not None:
        if current_user is None:
            raise HTTPException(status_code=401, detail="Unauthorized: user collection specified but no user authenticated")
        collections = await searcher.userCollection.read_all(str(current_user.id))
        user_collection_ids = {str(col.id) for col in collections}
        if req.user_collection_id not in user_collection_ids:
            raise HTTPException(status_code=403, detail="Forbidden: user does not have access to the specified collection")

    # </authorization>

    response = await searcher.textChunk.search(req)
    await summarizer(req, response)

    response.time_spent = time.time() - start_time
    return response


@exp_router.post("/api/summarize/{summary_type}", response_model=schemas.SummaryResponse)
async def summarize(search_response: schemas.SearchResponse, summary_type: str,
                    summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                    current_user: User | None = Depends(current_active_optional_user)) -> schemas.SummaryResponse:
    start_time = time.time()
    if summary_type != "results":
        # only "results" is supported now
        raise HTTPException(status_code=400, detail=f"Unknown summary type: {summary_type}")

    summary = await summarizer.gen_results_summary(
        search_response.search_request.query,
        search_response.results,
    )
    time_spent = time.time() - start_time
    return schemas.SummaryResponse(
        summary=summary,
        time_spent=time_spent,
    )


@exp_router.post("/api/question/{question_text}", response_model=schemas.SummaryResponse)
async def question(search_response: schemas.SearchResponse, question_text: str,
                   current_user: User | None = Depends(current_active_optional_user)) -> schemas.SummaryResponse:
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
