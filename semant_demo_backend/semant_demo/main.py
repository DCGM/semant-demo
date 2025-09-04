from fastapi import FastAPI, Depends, HTTPException
import os
import openai
from semant_demo import schemas
from semant_demo.config import config
import logging
from semant_demo.weaviate_search import WeaviateSearch
import asyncio
from time import time

logging.basicConfig(level=logging.INFO)

openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)

global_searcher = None
async def get_search() -> WeaviateSearch:
    global global_searcher
    if global_searcher is None:
        global_searcher = await WeaviateSearch.create(config)
    return global_searcher
app = FastAPI()


@app.post("/api/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest, searcher: WeaviateSearch = Depends(get_search)) -> schemas.SearchResponse:
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

@app.post("/api/rag", response_model=schemas.RagResponse)
async def rag(request: schemas.RagQuestionRequest, searcher: WeaviateSearch = Depends(get_search)) -> schemas.RagResponse:

    # build your snippets with IDs
    snippets = [
        f"[doc{i+1}]" + res.text.replace('\\n', ' ')
        for i, res in enumerate(request.search_response.results)
    ]
    context_string = "\n".join(snippets)

    # prompt
    system_prompt = (
        "You are a helpful chatbot.\n"
        "Use only the following pieces of context to answer the question. "
        "Don't make up any new information. If you can not provide answer based on the context, answer only \"I can´t answer the question.\".\n"
        "Format your answer using Markdown for clarity (e.g., bullet points for lists, bold for key terms).\n"
        "Context:\n"
        f"{context_string}"
    )

    # call ollama
    try:
        t1 = time()
        
        generated_answer = await searcher.ollama_proxy.call_ollama_chat(
            model=searcher.ollama_model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': request.question},
            ]
        )
        time_spent = time() - t1

    except Exception as e:
        logging.error(f"RAG error: calling Ollama: {e}")
        raise HTTPException(status_code=503, detail="RAG error: Service is not avalaible.")

    # answer
    return schemas.RagResponse(
        rag_answer=generated_answer.strip(),
        time_spent=time_spent
    )