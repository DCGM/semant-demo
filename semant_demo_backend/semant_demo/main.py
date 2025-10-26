import logging

import openai
from fastapi import FastAPI, Depends, HTTPException

from semant_demo import schemas
from semant_demo.config import config
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.rag.rag_generator import RagGenerator
from time import time

logging.basicConfig(level=logging.INFO)

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

async def get_rag(searcher: WeaviateSearch = Depends(get_search)) -> RagGenerator:
    global global_rag
    if global_rag is None:
        global_rag = RagGenerator(config=config, search=searcher)
    return global_rag

app = FastAPI()


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

@app.post("/api/rag", response_model=schemas.RagResponse)
async def rag(request: schemas.RagRequest, rag_generator: RagGenerator = Depends(get_rag)) -> schemas.RagResponse:
    #get history if exists
    if request.history:
        history_preprocessed = [msg.model_dump() for msg in request.history]
    else:
        history_preprocessed = []

    # call model
    try:
        t1 = time()

        generated_result = await rag_generator.generate_answer(
            rag_config = request.rag_config,
            question_string = request.question,
            history= history_preprocessed,
            #search parameters
            search_type=request.search_type,
            alpha=request.alpha,
            limit=request.limit,
            search_query = request.search_query
        )
        time_spent = time() - t1

    except Exception as e:
        logging.error(f"RAG error: calling model {request.model_name}: {e}")
        raise HTTPException(status_code=503, detail="RAG error: Service is not avalaible.")

    # answer
    return schemas.RagResponse(
        rag_answer=generated_result["answer"].strip(),
        sources=generated_result["sources"],
        time_spent=time_spent
    )