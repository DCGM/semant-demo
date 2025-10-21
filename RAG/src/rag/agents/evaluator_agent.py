import yaml
from typing import Dict, Any
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from rag.components.models import get_configured_model


class EvaluatorAgent:    
    def __init__(self, debug_level=0):
        self.debug_level = debug_level
        self.model = get_configured_model("generation")
        self.config = self._load_config()
        self.schema = self.config.get("schema", {})
        self.json_parser = JsonOutputParser()
        self.evaluation_prompt = self._load_prompt_template()
    
    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/agents.yaml", 'r') as file:
                config = yaml.safe_load(file)
            
            evaluator_config = config.get("evaluator-agent", {})
            
            if not evaluator_config:
                raise ValueError("evaluator-agent config not found")
            
            return evaluator_config
            
        except Exception as e:
            raise ValueError(f"Could not load config: {e}")
    
    def _load_prompt_template(self) -> PromptTemplate:
        try:
            prompts = self.config.get("prompts", {})
            evaluation_prompt = prompts.get("evaluation_prompt", "")
            
            if not evaluation_prompt:
                raise ValueError("evaluation_prompt not found in config")
            
            # Add JSON format instructions
            json_format_instructions = self.json_parser.get_format_instructions()
            enhanced_prompt = f"{evaluation_prompt}\n\n{json_format_instructions}"
            
            return PromptTemplate.from_template(enhanced_prompt)
            
        except Exception as e:
            raise ValueError(f"Could not load prompt template: {e}")
    
    async def evaluate_retrieval(self, query: str, query_analysis: Dict[str, Any], 
                          retrieved_results: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Convert parameters to strings for prompt formatting
            retrieved_results_str = str(retrieved_results)
            query_analysis_str = str(query_analysis)
            
            # Create chain with prompt, model, and parser
            chain = self.evaluation_prompt | self.model | self.json_parser
            
            # Get structured evaluation
            evaluation = await chain.ainvoke({
                "query": query,
                "query_analysis": query_analysis_str,
                "retrieved_results": retrieved_results_str
            })
            
            return {
                "query": query,
                "score": evaluation.get("score", 5),
                "needs_correction": evaluation.get("needs_correction", False)
            }
            
        except Exception as e:
            print(f"ERROR: {str(e)}")
            return {
                "query": query,
                "score": 5,
                "needs_correction": True,
                "error": f"Error evaluating retrieval: {str(e)}"
            }
    