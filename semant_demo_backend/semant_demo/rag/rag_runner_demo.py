#this is showcase of how to use rag without starting whole aplication
import asyncio
from dotenv import load_dotenv
load_dotenv() #have to be called before config import

from semant_demo.config import config
from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.rag.rag_generator import RagGenerator
from semant_demo.schemas import RagConfig, RagSearch



async def main():
    search = await WeaviateSearch.create(config=config)
    rag_generator = RagGenerator(config=config, search=search)
    # question/query - in this case its use as both rag question and search question
    question = "Vyskytly se v Praze neštovice po roce 1800?"
    print(f"Question: {question}\n")
    try:
        #configuration of the model - api, model, temperature
        model_config = RagConfig(
            model_name="OLLAMA",
            temperature=0.0
        )
        # create search query, will by used to create weaviate search query
        rag_search = RagSearch(
            search_query = question,
            limit= 5,
            search_type = 'hybrid', #vector: alpha=1, text: alpha=0
            alpha= 0.5,
            min_year= None,
            max_year= None,
            min_date= None,
            max_date=None,
            language= None
        )
   
        #call rag
        generated_result = await rag_generator.generate_answer(
            question_string = question,
            history= [],
            #rag configuration parameters
            rag_config = model_config,
            #search parameters
            rag_search = rag_search
        )

        print(f"Answer: {generated_result["answer"]}\n")
        if (False):
            print(f"Sources: {generated_result["sources"]}\n")

    except Exception as e:
        print(f"RAG error: while generating response: {e}")
    finally:
        await search.close()

if __name__ == "__main__":
    asyncio.run(main())