"""Runs one RAG configuration without starting the application (a developer demo that
calls the configured providers): ``python -m semant_demo.features.rag.run_demo``."""
import os
import asyncio
import warnings
from dotenv import load_dotenv
load_dotenv() #have to be called before config import

from semant_demo.config import SCRIPT_PATH, config
from semant_demo.adapters.llm.gateway import LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.bootstrap import load_search_vectors
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.features.search.service import SearchBackends, public_retriever
from semant_demo.features.rag.registry import rag_load_single_config
from semant_demo.features.rag.schemas import RagRequest, RagSearch


warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed.*<socket.socket.*>")
warnings.filterwarnings("ignore",category=ResourceWarning, message="unclosed transport.*")

async def main():
    client = await connect_weaviate(config)
    names = config.collectionNames
    retrieve = public_retriever(SearchBackends(
        chunks=ChunkSearchRepository(client, names),
        collections=UserCollectionRepository(client, names),
        tags=TagRepository(client, names),
        vectors=load_search_vectors(config),
    ))
    # question/query
    question = "Vyskytly se v Praze neštovice po roce 1800?"
    print(f"Question: {question}\n")
    try:
        #path to configuration
        path = os.path.join(SCRIPT_PATH, "configs", "rag", "configs", "01_ollama_default_config .yaml")
        #load configuration (yaml format)
        llm = LlmGateway(ModelCatalog.load(config.LLM_MODELS_CONFIG), ProviderSettings.from_config(config))
        results = rag_load_single_config(config, path, llm)
        if (results == None):
            return

        _, _, rag_generator = results

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
        generated_result = await rag_generator.rag_request(rag_request, retrieve=retrieve)

        print(f"Answer: {generated_result.rag_answer}\n")
        if (False):
            print(f"Sources: {generated_result.sources}\n")

    except Exception as e:
        print(f"RAG error: while generating response: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())