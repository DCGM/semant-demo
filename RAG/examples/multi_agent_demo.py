import sys
import requests
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

from rag.main import Agentic_RAG_app
from loguru import logger


def check_ollama_connection():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [model["name"] for model in models]
            
            # required_models = ["gemma3:1b", "nomic-embed-text:latest"]
            # missing_models = [model for model in required_models if model not in model_names]
            
            # if missing_models:
            #     print(f"Warning: Missing models: {missing_models}")
            #     print("Please pull the missing models with:")
            #     for model in missing_models:
            #         print(f"  ollama pull {model}")
            #     return False
            
            print("Ollama is running and all required models are available")
            print(f"Available models: {model_names}")
            return True
        else:
            print("Ollama is not responding properly")
            return False
            
    except requests.exceptions.ConnectionError:
        print("Cannot connect to Ollama. Please ensure Ollama is running on localhost:11434")
        return False
    except Exception as e:
        print(f"Error checking Ollama: {e}")
        return False


async def demo_multi_agent_workflow():    
    print("Agentic RAG Multi-Agent System Demo")
    print("=" * 60)

    if not check_ollama_connection():
        print("\nPlease fix the Ollama setup before running the demo.")
        return
    
    print("\nInitializing Agentic RAG application...")
    
    try:
        app = Agentic_RAG_app()
        print("Application initialized successfully")
    except Exception as e:
        print(f"Failed to initialize application: {e}")
        return
    
    queries = [
        {
            "query": "Testovací dotaz",
        },
        {
            "query": "Explain the basics of algebra",
        },
        {
            "query": "elektrická tramvaj",
        },
    ]


    # query_index = int(input("Enter the index of the query to run: "))
    query_index = 1
    query = queries[query_index]["query"]
    
    print(f"\nRunning multi-agent workflow demonstrations...")
    print("=" * 60)
    

    print(f"\n  Demo Query {query_index}: {query}")
    print("-" * 50)
    
    try:
        response = await app.chat(query)

        print(f"\n  Final Response:")
        print(f"{response}")
        
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    
    print("\n  Multi-Agent Demo completed!")
  

async def main():
    try:
        print("Starting Agentic RAG Demo with Local Ollama Models")
        print("=" * 60)
        
        await demo_multi_agent_workflow()
        
    except Exception as e:
        logger.error(f"Demo error: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())