import os
import yaml
from typing import Dict, Any, List
from dotenv import load_dotenv
from loguru import logger
from .agents.orchestrator import OrchestratorAgent
from .components.models import get_configured_model
from .components.vectorstores import vectorstores
from .components.graph_visualizer import GraphVisualizer


# Load environment variables
load_dotenv()


class Agentic_RAG_app:
    def __init__(self, debug_level: int = 1):
        """Initialize the RAG application.
        
        Args:
            debug_level: Debug level (0=none, 1=basic, 2=full)
        """
        self.debug_level = debug_level
        self.agent = None
        self.vectorstore = None
        self.graph_visualizer = None
        self._initialize_components()
    
    def _load_configurations(self):
        """Load configuration files."""
        configs = {}
        config_files = [
            "config/models.yaml",
            "config/vectorstores.yaml", 
            "config/agents.yaml"
        ]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                with open(config_file, 'r') as file:
                    config_name = os.path.basename(config_file).replace('.yaml', '')
                    configs[config_name] = yaml.safe_load(file)
                    logger.info(f"Loaded configuration: {config_file}")
            else:
                logger.warning(f"Configuration file not found: {config_file}")
        
        return configs
    
    def _initialize_components(self):
        try:
            configs = self._load_configurations()
            
            embedding_model = get_configured_model("embedding")
            generation_model = get_configured_model("generation")
            logger.info("Models initialized successfully")
            logger.info(f"Using embedding model: {embedding_model.model}")
            logger.info(f"Using generation model: {generation_model.model}")

            vectorstore_config = configs.get("vectorstores", {}).get("vectorstore", {})
            store_id = vectorstore_config.get("store_id", "CHROMA_DB")
            
            vectorstore_kwargs = {
                "collection_name": vectorstore_config.get("collection_name", "rag_content"),
                "embedding_function": embedding_model
            }
            
            if store_id == "CHROMA_DB":
                vectorstore_kwargs["persist_directory"] = vectorstore_config.get("persist_directory", "vectordb/chroma")
            elif store_id == "WEAVIATE_DB":
                vectorstore_kwargs["host"] = vectorstore_config.get("host", "127.0.0.1")
                vectorstore_kwargs["port"] = vectorstore_config.get("port", 8089)
                vectorstore_kwargs["grpc_port"] = vectorstore_config.get("grpc_port", 50059)
                vectorstore_kwargs["api_key"] = vectorstore_config.get("api_key")
                vectorstore_kwargs["collection_name"] = vectorstore_config.get("collection_name", "Chunks")
            
            self.vectorstore = vectorstores.get(store_id, **vectorstore_kwargs)
            logger.info(f"Vector store ({store_id}) initialized successfully")
            
            try:
                if hasattr(self.vectorstore, 'get_collection_info'):
                    collection_info = self.vectorstore.get_collection_info()
                    if 'total_count' in collection_info:
                        logger.info(f"Vector store contains {collection_info['total_count']} documents")
                    else:
                        logger.warning(f"Could not get collection info: {collection_info.get('error', 'Unknown error')}")
                else:
                    doc_count = self.vectorstore._collection.count()
                    logger.info(f"Vector store contains {doc_count} documents")
            except Exception as e:
                logger.warning(f"Could not access vector store collection: {e}")
            
            self.agent = OrchestratorAgent(vectorstore=self.vectorstore, debug_level=self.debug_level)
            logger.info("Multi-agent orchestrator initialized successfully")
            
            self.graph_visualizer = GraphVisualizer(debug_level=self.debug_level)
            logger.info("Graph visualizer initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing components: {e}")
            raise
    
    async def chat(self, message: str) -> str:
        """Chat with the orchestrator agent.
        
        Args:
            message: User message
            
        Returns:
            Agent response
        """
        try:
            if message.strip().lower() == "/visualize":
                if not self.agent or not self.graph_visualizer:
                    return "Error: Agent or graph visualizer not initialized"
                
                workflow_graph = self.agent.workflow
                ascii_graph = self.graph_visualizer.get_ascii_graph(workflow_graph)
                return ascii_graph
            
            if not self.agent:
                raise ValueError("Agent not initialized")
            
            result = await self.agent.process_query(message)
            if result.get("success", False):
                self.last_result = result
                return result.get("response", "No response generated")
            else:
                return result.get("response", f"Error: {result.get('error', 'Unknown error')}")
            
        except Exception as e:
            logger.error(f"Error in chat: {e}")
            return f"Error: {str(e)}"
    
    def get_last_response_data(self) -> Dict[str, Any]:
        return getattr(self, 'last_result', {})
    
    def get_retrieved_sources(self) -> List[Dict[str, Any]]:
        full_data = self.get_last_response_data()
        response_data = full_data.get('response_data', {})
        retrieved_info = response_data.get('retrieved_information', {})
        return retrieved_info.get('knowledge_base_results', [])
    
    def get_evaluation_results(self) -> Dict[str, Any]:
        full_data = self.get_last_response_data()
        response_data = full_data.get('response_data', {})
        return response_data.get('evaluation_results', {})
    
    def get_query_analysis(self) -> Dict[str, Any]:
        full_data = self.get_last_response_data()
        response_data = full_data.get('response_data', {})
        return response_data.get('query_analysis', {})


async def main():
    try:
        app = Agentic_RAG_app()
        
        print("RAG Assistant - Type 'quit' to exit")
        print("Available commands:")
        print("  /visualize - Show workflow graph")
        print("=" * 50)
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if not user_input:
                continue
            
            response = await app.chat(user_input)
            print(f"\nAssistant: {response}")
            
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        logger.error(f"Application error: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())