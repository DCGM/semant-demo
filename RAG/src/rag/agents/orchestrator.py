import yaml
from typing import Dict, Any, List, TypedDict
from langgraph.graph import StateGraph, END, START
from langchain_core.messages import HumanMessage, BaseMessage
from rag.agents.query_analyzer import QueryAnalyzerAgent
from rag.agents.retrieval_agent import RetrievalAgent
from rag.agents.evaluator_agent import EvaluatorAgent
from rag.agents.response_generator import BasicResponseGenerator, ResponseGeneratorAgent
from rag.components.workflow_loader import load_workflow_config, validate_workflow_config
from loguru import logger


class OrchestratorState(TypedDict):
    messages: List[BaseMessage]
    query: str
    query_analysis: Dict[str, Any]
    retrieved_information: Dict[str, Any]
    evaluation_results: Dict[str, Any]
    response_generated: Dict[str, Any]
    final_response: str
    needs_correction: bool
    correction_attempts: int


class OrchestratorAgent:    
    def __init__(self, vectorstore=None, debug_level=0, workflow_config_path="config/workflow.yaml"):
        self.debug_level = debug_level
        self.workflow_config_path = workflow_config_path
        self.max_correction_attempts = self._load_config()
        self.vectorstore = vectorstore  # Store vectorstore for cleanup
        
        # Initialize all agents
        self.query_analyzer = QueryAnalyzerAgent()
        self.retrieval_agent = RetrievalAgent(vectorstore=vectorstore, debug_level=debug_level)
        self.evaluator_agent = EvaluatorAgent(debug_level=debug_level)
        self.basic_response_generator = BasicResponseGenerator()
        self.response_generator = ResponseGeneratorAgent(debug_level=debug_level)
        
        # Create the workflow graph using config-driven approach
        self.workflow = self._create_workflow_from_config()
    
    def _load_config(self) -> int:
        """Load configuration from agents.yaml file."""
        try:
            with open("config/agents.yaml", 'r') as file:
                config = yaml.safe_load(file)
            
            orchestrator_config = config.get("orchestrator-agent", {})
            return orchestrator_config.get("max_correction_attempts", 2)
            
        except Exception as e:
            logger.warning(f"Could not load orchestrator config: {e}")
            return 2
    
    def _create_workflow_from_config(self) -> StateGraph:
        try:
            # Validate the workflow configuration first
            if not validate_workflow_config(self.workflow_config_path):
                logger.warning("Workflow config validation failed, falling back to hardcoded workflow")
            
            # Create workflow using hardcoded nodes but config-driven edges
            workflow = self._create_workflow_with_config_edges()
            
            logger.info("Loaded config-driven workflow with hardcoded nodes")
            
            return workflow
            
        except Exception as e:
            logger.error(f"Failed to create workflow from config: {e}")
            logger.warning("Falling back to hardcoded workflow")
    
    def _create_workflow_with_config_edges(self) -> StateGraph:
        workflow = StateGraph(OrchestratorState)
        
        # Add all nodes (hardcoded)
        workflow.add_node("query_analyzer", self._query_analyzer_node)
        workflow.add_node("retrieval_agent", self._retrieval_agent_node)
        workflow.add_node("evaluator_agent", self._evaluator_agent_node)
        workflow.add_node("response_generator", self._response_generator_node)
        workflow.add_node("basic_response_generator", self._basic_response_generator_node)
        workflow.add_node("correction_handler", self._correction_handler_node)
        
        try:
            config = load_workflow_config(self.workflow_config_path)
            
            # Add edges from configuration
            for edge_def in config.get('edges', []):
                src = edge_def['from']
                
                # Handle direct edges
                if 'to' in edge_def:
                    dst = edge_def['to']
                    
                    if dst == 'END':
                        workflow.add_edge(src, END)
                    elif src == 'START':
                        workflow.add_edge(START, dst)
                    else:
                        workflow.add_edge(src, dst)
                    
                    logger.debug(f"Added config edge: {src} -> {dst}")
                
                elif 'conditional' in edge_def:
                    cond = edge_def['conditional']
                    
                    # Use the _should_correct method directly
                    router_function = self._should_correct
                    
                    branches = cond['branches']
                    
                    workflow.add_conditional_edges(src, router_function, branches)
                    
                    logger.debug(f"Added config conditional edge: {src} -> {cond['function']} -> {list(branches.keys())}")
            
            # Set entry point from config
            entry_point = config.get('entry_point')
            if entry_point:
                workflow.set_entry_point(entry_point)
                logger.debug(f"Set entry point from config: {entry_point}")
            else:
                workflow.set_entry_point("query_analyzer")
                logger.debug("Set default entry point: query_analyzer")
                
        except Exception as e:
            logger.warning(f"Failed to load edges from config: {e}")
            logger.warning("Using hardcoded edges as fallback")
            # Fallback to hardcoded edges - TODO: remove this
            workflow.add_edge("query_analyzer", "retrieval_agent")
            workflow.add_edge("retrieval_agent", "evaluator_agent")
            workflow.add_conditional_edges(
                "evaluator_agent",
                self._should_correct,
                {
                    "correct": "correction_handler",
                    "proceed": "response_generator"
                }
            )
            workflow.add_edge("correction_handler", "retrieval_agent")
            workflow.add_edge("response_generator", END)
            workflow.set_entry_point("query_analyzer")
        
        return workflow.compile()
    
    def _should_correct(self, state: Dict[str, Any]) -> str:
        evaluation_results = state.get("evaluation_results", {})
        needs_correction = evaluation_results.get("needs_correction", False)
        correction_attempts = state.get("correction_attempts", 0)
        
        if needs_correction and correction_attempts < self.max_correction_attempts:
            return "correct"
        else:
            return "proceed"
    
    async def _query_analyzer_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = state.get("query", "")
            if not query:
                return {"error": "No query available for analysis"}
            
            if self.debug_level >= 1:
                logger.info(f"\n  Query Analyzer Agent: Analyzing query: '{query}'")
            
            # Analyze the query
            query_analysis = await self.query_analyzer.analyze_query(query)
            
            if self.debug_level >= 1:
                logger.info(f"    Query analysis completed: {query_analysis.get('is_valid', 'unknown')}")
            
            return {
                "query_analysis": query_analysis
            }
            
        except Exception as e:
            logger.error(f"Error in query analysis: {str(e)}")
            return {
                "error": f"Error in query analysis: {str(e)}",
                "query_analysis": {"is_valid": False, "refined_query": state.get("query", "")}
            }
    
    async def _retrieval_agent_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = state.get("query", "")
            query_analysis = state.get("query_analysis", {})
            
            if not query:
                return {"error": "No query available for retrieval"}
            
            if self.debug_level >= 1:
                logger.info(f"\n  Retrieval Agent: Retrieving information for: '{query}'")
            
            retrieved_information = await self.retrieval_agent.retrieve_information(query, query_analysis)
            
            if self.debug_level >= 1:
                results_count = len(retrieved_information.get("knowledge_base_results", []))
                logger.info(f"    Retrieved {results_count} results")
            
            return {
                "retrieved_information": retrieved_information
            }
            
        except Exception as e:
            logger.error(f"Error in information retrieval: {str(e)}")
            return {
                "error": f"Error in information retrieval: {str(e)}",
                "retrieved_information": {"knowledge_base_results": [], "retrieval_quality": "poor"}
            }
    
    async def _evaluator_agent_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = state.get("query", "")
            query_analysis = state.get("query_analysis", {})
            retrieved_information = state.get("retrieved_information", {})
            
            if not query:
                return {"error": "No query available for evaluation"}
            
            if self.debug_level >= 1:
                logger.info(f"\n  Evaluator Agent: Evaluating retrieval quality for: '{query}'")
            
            evaluation_results = await self.evaluator_agent.evaluate_retrieval(
                query, query_analysis, retrieved_information
            )
            
            if self.debug_level >= 1:
                score = evaluation_results.get("score", 0)
                needs_correction = evaluation_results.get("needs_correction", False)
                logger.info(f"    Evaluation completed - Score: {score}, Needs correction: {needs_correction}")
            
            return {
                "evaluation_results": evaluation_results,
                "needs_correction": evaluation_results.get("needs_correction", False)
            }
            
        except Exception as e:
            logger.error(f"Error in evaluation: {str(e)}")
            return {
                "error": f"Error in evaluation: {str(e)}",
                "evaluation_results": {"score": 5, "needs_correction": True},
                "needs_correction": True
            }
    
    async def _correction_handler_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = state.get("query", "")
            evaluation_results = state.get("evaluation_results", {})
            retrieved_information = state.get("retrieved_information", {})
            correction_attempts = state.get("correction_attempts", 0)
            
            if self.debug_level >= 1:
                logger.info(f"\n  Correction Handler: Attempting correction {correction_attempts + 1}")
                logger.info(f"    Correction attempt {correction_attempts + 1} initiated")
            
            refined_query = await self.retrieval_agent.refine_query(
                query, retrieved_information, evaluation_results
            )
            
            if self.debug_level >= 1:
                logger.info(f"    Original query: '{query}'")
                logger.info(f"    Refined query: '{refined_query}'")
            
            return {
                "query": refined_query,  # Update the query with the refined version
                "correction_attempts": correction_attempts + 1,
                "needs_correction": False  # Reset for next iteration
            }
            
        except Exception as e:
            logger.error(f"Error in correction handling: {str(e)}")
            return {
                "error": f"Error in correction handling: {str(e)}",
                "needs_correction": False,
                "correction_attempts": state.get("correction_attempts", 0) + 1
            }
    
    async def _response_generator_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = state.get("query", "")
            query_analysis = state.get("query_analysis", {})
            retrieved_information = state.get("retrieved_information", {})
            evaluation_results = state.get("evaluation_results", {})
            
            if not query:
                return {"error": "No query available for response generation"}
            
            if self.debug_level >= 1:
                logger.info(f"\n  Response Generator Agent: Generating response for: '{query}'")
            
            response_generated = await self.response_generator.generate_response(
                query, query_analysis, retrieved_information, evaluation_results
            )
            
            response_length = len(response_generated.get("response_text", ""))
            if self.debug_level >= 1:
                logger.info(f"    Response generated: {response_length} characters")
            
            return {
                "response_generated": response_generated
            }
            
        except Exception as e:
            logger.error(f"Error in response generation: {str(e)}")
            return {
                "error": f"Error in response generation: {str(e)}",
                "response_generated": {
                    "response_text": f"I apologize, but I encountered an error: {str(e)}"
                }
            }
    
    async def _basic_response_generator_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = state.get("query", "")
            query_analysis = state.get("query_analysis", {})
            retrieved_information = state.get("retrieved_information", {})
            evaluation_results = state.get("evaluation_results", {})
            
            if not query:
                return {"error": "No query available for response generation"}
            
            if self.debug_level >= 1:
                logger.info(f"\n  Basic Response Generator Agent: Generating response for: '{query}'")
            
            response_generated = await self.basic_response_generator.generate_response(
                query, query_analysis, retrieved_information, evaluation_results
            )
            
            response_length = len(response_generated.get("response_text", ""))
            if self.debug_level >= 1:
                logger.info(f"    Response generated: {response_length} characters")
            
            return {
                "response_generated": response_generated
            }
            
        except Exception as e:
            logger.error(f"Error in basic response generation: {str(e)}")
            return {
                "error": f"Error in basic response generation: {str(e)}",
                "response_generated": {
                    "response_text": f"I apologize, but I encountered an error: {str(e)}"
                }
            }
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        try:
            if self.debug_level >= 1:
                logger.info("=" * 60)
                logger.info(f"Processing query: '{query}'")
                logger.info("=" * 60)
            
            # Initialize state
            initial_state = {
                "messages": [HumanMessage(content=query)],
                "query": query,
                "query_analysis": {},
                "retrieved_information": {},
                "evaluation_results": {},
                "response_generated": {},
                "final_response": "",
                "needs_correction": False,
                "correction_attempts": 0
            }
            
            result = await self.workflow.ainvoke(initial_state)
            
            if self.debug_level >= 1:
                logger.info(f"\n  Workflow completed successfully!")
                logger.info("=" * 60)
            
            response_generated = result.get("response_generated", {})
            final_response = response_generated.get("response_text", "")
            
            return {
                "success": True,
                "query": result.get("query", query),
                "response": final_response,
                "response_data": response_generated,
                "query_analysis": result.get("query_analysis", {}),
                "retrieved_information": result.get("retrieved_information", {}),
                "evaluation_results": result.get("evaluation_results", {}),
                "correction_attempts": result.get("correction_attempts", 0)
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return {
                "success": False,
                "error": f"Error processing query: {str(e)}",
                "query": query,
                "response": "I apologize, but I encountered an error while processing your request. Please try again."
            }
        finally:
            # Close vectorstore connections if they exist - TODO: this in vectorstore component is super ugly and complex
            if hasattr(self, 'vectorstore') and self.vectorstore:
                try:
                    if hasattr(self.vectorstore, 'close'):
                        self.vectorstore.close()
                        logger.info("Vectorstore connection closed")
                    if hasattr(self.vectorstore, 'aclose'):
                        await self.vectorstore.aclose()
                        logger.info("Vectorstore async connection closed")
                except Exception as e:
                    logger.warning(f"Error closing vectorstore: {e}")


def create_orchestrator_agent(vectorstore=None, debug_level=0) -> OrchestratorAgent:
    return OrchestratorAgent(vectorstore=vectorstore, debug_level=debug_level)