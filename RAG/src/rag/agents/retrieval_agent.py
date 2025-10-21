from typing import Dict, Any, List
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from rag.components.models import models


class RetrievalAgent:    
    def __init__(self, vectorstore, debug_level=0):
        if vectorstore is None:
            raise ValueError("vectorstore parameter is required. Use vectorstores factory to create vectorstore instance.")
        
        self.model = models.get("OLLAMA_GENERATION_MODEL")
        self.embedding_model = models.get("OLLAMA_EMBEDDING_MODEL")
        self.vectorstore = vectorstore
        self.debug_level = debug_level
        self.max_results_per_source = self._load_config()
    
    def _load_config(self) -> int:
        try:
            import yaml
            with open("config/agents.yaml", 'r') as file:
                config = yaml.safe_load(file)
            
            retrieval_config = config.get("retrieval-agent", {})
            max_results = retrieval_config.get("max_results_per_source", 1)
            return max_results
            
        except Exception as e:
            # Default to 1 if config can't be loaded
            return 1
    
    async def retrieve_information(self, query: str, query_analysis: Dict[str, Any], correction_attempts: int = 0) -> Dict[str, Any]:
        try:
            if correction_attempts > 0 and query_analysis.get("refined_query"):
                search_query = query_analysis.get("refined_query")
            else:
                search_query = query

            results = {
                "query": query,
                "search_query": search_query,
                "knowledge_base_results": [],
                "retrieval_quality": "unknown"
            }
            
            content_results = await self._search_content_base(search_query)
            results["knowledge_base_results"] = [
                result for result in content_results 
                if "error" not in result
            ][:self.max_results_per_source]
            return results
            
        except Exception as e:
            return {
                "query": query,
                "error": f"Error retrieving information: {str(e)}",
                "knowledge_base_results": [],
                "retrieval_quality": "poor"
            }
    
    async def _search_content_base(self, query: str) -> List[Dict[str, Any]]:
        try:
            docs = await self.vectorstore.asimilarity_search(query, k=self.max_results_per_source)
            formatted_results = self._format_search_results(docs, "content")
            return formatted_results
        except Exception as e:
            return [{"error": f"Content base search error: {str(e)}"}]
    
    def _format_search_results(self, docs: List[Document], source_type: str) -> List[Dict[str, Any]]:
        results = []
        for i, doc in enumerate(docs, 1):
            result = {
                "rank": i,
                "content": doc.page_content,
                "source": doc.metadata.get('source', 'Unknown source'),
                "source_type": source_type,
                "relevance_score": 1.0 - (i * 0.1),  # Simple ranking score
                "metadata": doc.metadata
            }
            results.append(result)
        return results
    
    async def refine_query(self, original_query: str, retrieved_information: Dict[str, Any], 
                           evaluation_results: Dict[str, Any]) -> str:
        try:
            failed_results = retrieved_information.get("knowledge_base_results", [])
            
            prompt_template = self._load_refinement_prompt_template()
            prompt = prompt_template.format(
                original_query=original_query,
                failed_results=failed_results
            )

            response = await self.model.ainvoke(prompt)
            refined_query = response.content.strip()

            return refined_query
            
        except Exception as e:
            return f"detailed information about {original_query}"
    
    def _load_refinement_prompt_template(self) -> PromptTemplate:
        try:
            import yaml
            with open("config/agents.yaml", 'r') as file:
                config = yaml.safe_load(file)
            
            retrieval_config = config.get("retrieval-agent", {})
            prompts = retrieval_config.get("prompts", {})
            refinement_prompt = prompts.get("refinement_prompt", "")
            
            if not refinement_prompt:
                raise ValueError("refinement_prompt not found in config file")
            
            return PromptTemplate.from_template(refinement_prompt)
            
        except Exception as e:
            raise ValueError(f"Could not load refinement prompt from config: {e}")
