#env
import os
from dotenv import load_dotenv
#ragas openai
from langchain_openai import ChatOpenAI
from ragas.embeddings import OpenAIEmbeddings
import openai
#ragas ollama
from langchain_ollama import OllamaLLM
from langchain_community.embeddings import HuggingFaceEmbeddings
#ragas
from ragas import EvaluationDataset
from ragas import evaluate
from ragas.llms.base import llm_factory

from ragas import SingleTurnSample
from ragas.metrics import LLMContextPrecisionWithoutReference
#metrics imported as instances
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness
)
#backend 
import httpx
import json
import asyncio
import httpx
#others
from typing import List, Dict
import argparse

#colors for better logs in terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

#main class calling backend api
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
        if not self.search_response:
            raise ValueError("Search must be called before rag")
        
        print(f"--- Calling /api/rag: '{query}' ---")

        request_body = {
            "search_response": self.search_response,
            "question": query,
            "history": [],
            "model_name": model_name
        }
        #request
        response = await self.client.post(f"{self.backend_url}/api/rag", json=request_body, timeout=60.0)
        response.raise_for_status()
        answer = response.json()

        print("--- RAG API processed succesfuly. ---")

        return answer.get('rag_answer', 'ERROR no: "rag_answer".')

def loadDataFromJson ():
    return 

def loadDataFromTXT ():
    return 

async def main():
    #load config (.env)
    load_dotenv() 
    #get required variables
    rag_api = RAGAPI(os.getenv("BACKEND_API_URL"))
    parser = argparse.ArgumentParser(description="Evaluator for RAG.")
    parser.add_argument("--mode",
                        type=str,
                        default="NOGT",
                        choices=["NOGT", "GT"],
                        help="Evaluation mode: 'NOGT' (.json required) or 'GT' (.txt required) ")
    parser.add_argument("--rag_model",
                        type=str,
                        default="OLLAMA",
                        choices=["OLLAMA","GOOGLE", "OPENAI"],
                        help="Model used by RAG: 'OLLAMA', 'GOOGLE' or 'OPENAI' ")
    parser.add_argument("--eval_model",
                    type=str,
                    default="OLLAMA",
                    choices=["OLLAMA", "OPENAI"],
                    help="Model used for evaluation: 'OLLAMA' or 'OPENAI' ")
    parser.add_argument("--precission",
                    type=str,
                    default="OFF",
                    choices=["ON", "OFF"],
                    help="Only relevant in 'NOGT' mode. Precission choices: 'ON' or 'OFF' ")

    args = parser.parse_args()

    print(f"{Colors.GREEN} Starting evaluation in mode: {args.mode} with RAG model: {args.rag_model} and evaluation model: {args.eval_model} and precission: {args.precission}.{Colors.RESET} ")

    eval_model = args.eval_model
    rag_model = args.rag_model
    mode = args.mode
    precission_mode = False
    if (args.precission == "ON"):
        precission_mode = True

    #get desired evaluation model
    if (eval_model == "OPENAI"):
        eval_model_name = os.getenv("OPENAI_EVAL_MODEL")
        #API key is taken automaticly from env ( os.getenv("OPENAI_API_KEY") )
        llm = llm_factory(eval_model_name)
        openai_client = openai.OpenAI()
        embeddings = OpenAIEmbeddings(client=openai_client) #possibly required for GT eval
    elif(eval_model == "OLLAMA"):
        eval_model_name = os.getenv("OLLAMA_EVAL_MODEL")
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        llm = OllamaLLM(model=eval_model_name, base_url = ollama_url)
        embeddings = HuggingFaceEmbeddings()    #possibly required for GT eval
    else:
        print(f"\n Invalid model: {eval_model}. Possible models: [OPENAI, OLLAMA].")
        return

    print(f"--- Model used for evaluation is {eval_model} precisely: {eval_model_name} ---")
    #TODO: load questions from files
    #query = "Jaké byly výskyty vztekliny v Praze?"
    queries = ["Jaké byly výskyty vztekliny v Praze?", "Jaká byla situace v oblasti sudet v roce 1945?"]

    try:
        if (mode == "NOGT"):
            dataset = []
            context_precision = LLMContextPrecisionWithoutReference(llm=llm)
            precisions = []

            for query in queries:
                #search
                retrieved_context  = await rag_api.search(query, limit=os.getenv("CHUNK_LIMIT") )
                retrieved_contexts_text = [ctx['text'] for ctx in retrieved_context]
                #rag
                rag_answer = await rag_api.call_rag(query, rag_model)
                dataset.append(
                    {
                        "user_input":query,
                        "retrieved_contexts":retrieved_contexts_text,
                        "response":rag_answer
                    }
                )
                #calculating precission (current eval require GT to be able to calculate precission)
                if(precission_mode == True):
                    sample = SingleTurnSample(
                        user_input=query,
                        response=rag_answer,
                        retrieved_contexts=retrieved_contexts_text
                    )
                    #add precision of sample to list
                    precisions.append(await context_precision.single_turn_ascore(sample))

            evaluation_dataset = EvaluationDataset.from_list(dataset)

            print(f"---Starting evaluation ---")

            result = evaluate(dataset=evaluation_dataset,
                              metrics=[faithfulness, answer_relevancy],
                              llm=llm)
            
            print(f"{Colors.GREEN}---Evaluation finished ---{Colors.RESET}")
            print(result)
            if(precission_mode == True):
                average_precision = sum(precisions) / len(precisions)
                print(f"average_precission: {average_precision}")

        elif(mode == "GT"):
            pass
        else:
            print(f"\n Invalid mode: {mode}. Possible modes: [GT, NOGT].")

    except httpx.RequestError as e:
        print(f"\nRAG EVALUATION ERROR: Can not connect to backend on url: {os.getenv("BACKEND_API_URL")}..")
    except httpx.HTTPStatusError as e:
        print(f"\nRAG EVALUATION ERROR: API error code: {e.response.status_code}.")
        print("Error detail:", e.response.text)
    finally:
        if 'rag_api' in locals():
            await rag_api.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())