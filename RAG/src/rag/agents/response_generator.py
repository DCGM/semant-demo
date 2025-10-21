import yaml
from typing import Dict, Any
from langchain_core.prompts import PromptTemplate
from rag.components.models import get_configured_model


class ResponseGeneratorAgent:    
    def __init__(self, debug_level=0):
        self.debug_level = debug_level
        self.model = get_configured_model("generation")
        self.response_prompt = self._load_prompt_template()
    
    def _load_prompt_template(self) -> PromptTemplate:
        try:
            with open("config/agents.yaml", 'r') as file:
                config = yaml.safe_load(file)
            
            response_generator_config = config.get("response-generator-agent", {})
            prompts = response_generator_config.get("prompts", {})
            response_prompt = prompts.get("response_generation_prompt", "")
            
            if not response_prompt:
                raise ValueError("response_generation_prompt not found in config file")
            
            return PromptTemplate.from_template(response_prompt)
            
        except Exception as e:
            raise ValueError(f"Could not load response generation prompt from config: {e}")
    
    async def generate_response(self, query: str, query_analysis: Dict[str, Any], 
                        retrieved_information: Dict[str, Any], 
                        evaluation_results: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query_analysis_str = str(query_analysis)
            retrieved_info_str = str(retrieved_information)
            evaluation_str = str(evaluation_results)
            
            prompt = self.response_prompt.format(
                query=query,
                query_analysis=query_analysis_str,
                retrieved_information=retrieved_info_str,
                evaluation_results=evaluation_str
            )
            
            if self.debug_level >= 1:
                print(f"DEBUG: Generating response for query: '{query}'")
                # print(f"Using model: {self.model.model_name}")
            
            response = await self.model.ainvoke(prompt)
            
            # Return the direct response text
            return {
                "query": query,
                "response_text": response.content.strip(),
                "retrieved_information": retrieved_information,
                "evaluation_results": evaluation_results,
                "query_analysis": query_analysis
            }
            
        except Exception as e:
            print(f"ERROR in response generation: {str(e)}")
            return {
                "query": query,
                "error": f"Error generating response: {str(e)}",
                "response_text": "I apologize, but I encountered an error while generating a response. Please try rephrasing your question or ask about a different topic.",
                "retrieved_information": retrieved_information,
                "evaluation_results": evaluation_results,
                "query_analysis": query_analysis
            }


class BasicResponseGenerator:    
    def __init__(self):
        pass

    async def generate_response(self, query: str, query_analysis: Dict[str, Any], 
                        retrieved_information: Dict[str, Any], 
                        evaluation_results: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return {
                "query": query,
                "response_text": retrieved_information
            }
        
        except Exception as e:
            return {
                "query": query,
                "error": f"Error generating response: {str(e)}",
                "response_text": "I apologize, but I encountered an error while generating a response. Please try rephrasing your question or ask about a different topic."
            }


