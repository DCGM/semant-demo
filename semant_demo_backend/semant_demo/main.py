from fastapi import FastAPI
import os
import openai
import schemas
from config import config
import logging
from weaviate_search import WeaviateSearch

logging.basicConfig(level=logging.INFO)

openai.api_key = os.getenv(config.OPENAI_API_KEY)
search = WeaviateSearch.create(config)

app = FastAPI()


@app.post("/search", response_model=schemas.SearchResponse)
async def search(req: schemas.SearchRequest) -> schemas.SearchResponse:
    return search.search(req)


@app.post("/summarize/{summary_type}", response_model=schemas.SummaryResponse)
async def summarize(search_response: schemas.SearchResponse, summary_type: str) -> schemas.SummaryResponse:
    snippets = [res.text.replace('\n', ' ') for res in search_response.results]
    resp = openai.ChatCompletion.create(
      model="gpt-4o-mini", messages=[
            {
                "role": "system",
                "content": '\n'.join([
                    "You are a summarization assistant.",
                    "You will be given text snippets, each labeled with a unique ID like [doc1], [doc2], … [doc15].",
                    "You should produce a single, concise summary that covers all the key points relevant to a user search query.",
                    "After every fact that you extract from a snippet, append the snippet’s ID in square brackets—for example: “The gene ABC is upregulated in tumor cells [doc3].”",
                    "If multiple snippets support the same fact, list all their IDs separated by commas: “This approach improved accuracy by 12% [doc2, doc7, doc11].”",
                    "Do not introduce any facts that are not in the snippets. Focus on information that is relevant to the user query.",
                    "Write the summary clearly and concisely.",
                    "Keep the summary under 100 words."
                ])
            },
            {
                "role": "user",
                "content": '\n'.join(
                    [f'The user query is: "{search_response.search_request.query}"',
                      "Here are the retrieved text snippets:",
                      *snippets,
                      "",
                      "Please summarize these contexts, tagging each statement with its source ID. Do not add any other text."
                     ])
            }
        ]
    )

    return schemas.SummaryResponse(
        summary=resp.choices[0].message.content,
        time_spent=search_response.time_spent,
    )

