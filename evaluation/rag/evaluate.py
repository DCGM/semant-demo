#env
import os
from dotenv import load_dotenv
#ragas
from langchain_openai import ChatOpenAI
from ragas.embeddings import OpenAIEmbeddings
import openai
#backend 
import httpx
import json

import asyncio
from typing import List, Dict
import httpx

class RAGAPI:
    def __init__(self, backend_url):
        self.backend_url = backend_url
        self.search_result = None
        self.client = httpx.AsyncClient()

    #call weaviate search (/api/search)
    async def search(self, query: str, limit: int = 5) -> list:
        print(f"--- Calling /api/search: '{query}' ---")

        request_body = {
            "query": query,
            "limit": limit,
            #TODO: change while merged with search refactorization branch
            "search_title_generate": False,
            "search_summary_generate": False
            # "type": "hybrid",
            # "hybrid_search_alpha": 0.5
        }

        #request
        response = await self.client.post(f"{self.backend_url}/api/search", json=request_body, timeout=60.0)
        response.raise_for_status()
        self.search_response = response.json()

        print("--- Found:", len(self.search_response.get('results', [])), "chunks ---")
        return self.search_response.get('results', [])
    
    #call rag (/api/rag)
    async def call_rag(self, query: str, model_name: str) -> str:
        answer = ""
        return answer



async def main():
    load_dotenv() 
    rag_api = RAGAPI(os.getenv("BACKEND_API_URL"))
    #TODO: parse arguments
    eval_model = "OPENAI"
    rag_model = "OLLAMA"

    #get desired evaluation model
    #load config (.env)
    if (eval_model == "OPENAI"):
        eval_model_name = os.getenv("OPENAI_EVAL_MODEL")
        eval_model_API = os.getenv("OPENAI_API_KEY")
        llm = ChatOpenAI(model=eval_model_name)
        openai_client = openai.OpenAI()
        embeddings = OpenAIEmbeddings(client=openai_client)

    #TODO: load questions from files
    query = "Jaké byly výskyty vztekliny v Praze?"

    try:
        search_result = await rag_api.search(query)
        print(search_result)

    except requests.exceptions.RequestException as e:
        print(f"\nRAG EVALUATION ERROR: Cant connect to backend on url: {os.getenv("BACKEND_API_URL")}.")
        if e.response:
            print("Error detail:", e.response.status_code, e.response.text)


if __name__ == "__main__":
    asyncio.run(main())