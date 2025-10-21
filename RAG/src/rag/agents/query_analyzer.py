import yaml
from typing import Dict, Any
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from rag.components.models import get_configured_model


class QueryAnalyzerAgent:    
    def __init__(self):
        self.model = get_configured_model("generation")
        self.config = self._load_config()
        self.schema = self.config.get("schema", {})
        self.json_parser = JsonOutputParser()
        self.prompt_template = self._load_prompt_template()
    
    def _load_config(self) -> Dict[str, Any]:
        try:
            with open("config/agents.yaml", 'r') as file:
                config = yaml.safe_load(file)
            
            query_analyzer_config = config.get("query-analyzer-agent", {})
            
            if not query_analyzer_config:
                raise ValueError("query-analyzer-agent config not found")
            
            return query_analyzer_config
            
        except Exception as e:
            raise ValueError(f"Could not load config: {e}")
    
    def _load_prompt_template(self) -> PromptTemplate:
        try:
            prompts = self.config.get("prompts", {})
            analysis_prompt = prompts.get("analysis_prompt", "")
            
            if not analysis_prompt:
                raise ValueError("analysis_prompt not found in config")
            
            # Add JSON format instructions
            json_format_instructions = self.json_parser.get_format_instructions()
            enhanced_prompt = f"{analysis_prompt}\n\n{json_format_instructions}"
            
            return PromptTemplate.from_template(enhanced_prompt)
            
        except Exception as e:
            raise ValueError(f"Could not load prompt template: {e}")
    
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        try:
            # Create chain with prompt, model, and parser
            chain = self.prompt_template | self.model | self.json_parser
            
            # Get structured analysis using async invoke
            parsed_response = await chain.ainvoke({"query": query})
            
            return {
                "original_query": query,
                "is_valid": parsed_response.get("is_valid", True),
                "refined_query": parsed_response.get("refined_query", query)
            }
            
        except Exception as e:
            print(f"ERROR in query analysis: {str(e)}")
            return {
                "original_query": query,
                "is_valid": False,
                "refined_query": query,
                "error": f"Error analyzing query: {str(e)}"
            }
    