#this is showcase of how to use rag without starting whole aplication
import os
import asyncio
import warnings
from dotenv import load_dotenv
load_dotenv() #have to be called before config import

from semant_demo.config import config
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.rag.rag_factory import rag_load_single_config
from semant_demo.schemas import RagRequest, RagSearch

import semant_demo.rag.rag_generator

warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed.*<socket.socket.*>")
warnings.filterwarnings("ignore",category=ResourceWarning, message="unclosed transport.*")

async def main():
    searcher = await WeaviateSearch.create(config=config)
    # question/query
    question = "Vyskytly se v Praze neštovice po roce 1800?"
    print(f"Question: {question}\n")
    try:
        #path to configuration
        path = os.path.join(config.RAG_CONFIGS_PATH, "01_ollama_default_config .yaml")
        #load configuration (yaml format)
        results = rag_load_single_config(config, path)
        
        _, _, rag_generator = results

        if (results == None):
            return

        #create search
        rag_search = RagSearch(
            search_query=question   #with history its rephrased
        )
        #create request
        rag_request = RagRequest(
                question =  question,
                history = [],
                rag_search = rag_search
        )

        #call rag
        generated_result = await rag_generator.rag_request(rag_request, searcher=searcher)

        print(f"Answer: {generated_result.rag_answer}\n")
        if (False):
            print(f"Sources: {generated_result.sources}\n")

    except Exception as e:
        print(f"RAG error: while generating response: {e}")
    finally:
        await searcher.close()

if __name__ == "__main__":
    asyncio.run(main())