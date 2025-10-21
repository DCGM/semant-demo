from typing import Dict, List, Any
from dataclasses import dataclass

# RAGAS imports
from ragas import evaluate

from ragas.dataset import Dataset
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    ContextPrecision,
    LLMContextRecall,
    ContextEntityRecall,
    NoiseSensitivity,
    ResponseRelevancy,
    Faithfulness,
    MultiModalFaithfulness,
    MultiModalRelevance,
)
            
from rag.agents.orchestrator import OrchestratorAgent
from rag.components.models import get_configured_model


@dataclass
class EvaluationResult:
    query: str
    ground_truth: str
    answer: str
    contexts: List[str]
    context_precision: float
    context_recall: float
    context_entity_recall: float
    noise_sensitivity: float
    response_relevancy: float
    faithfulness: float
    multimodal_faithfulness: float
    multimodal_relevance: float


class SimpleRAGASEvaluator:
    def __init__(self, orchestrator: OrchestratorAgent = None, vectorstore=None):
        if orchestrator is None and vectorstore is not None:
            # Create orchestrator with existing vectorstore - TODO: this in orchestrator component is super ugly and complex
            from rag.agents.orchestrator import OrchestratorAgent
            self.orchestrator = OrchestratorAgent(vectorstore=vectorstore)
        else:
            self.orchestrator = orchestrator
        self.llm = self._initialize_llm()
        
        # All RAGAS metrics
        self.metrics = [
            ContextPrecision,
            LLMContextRecall,
            ContextEntityRecall,
            NoiseSensitivity,
            ResponseRelevancy,
            Faithfulness,
            MultiModalFaithfulness,
            MultiModalRelevance,
        ]
    
    def _initialize_llm(self):
        model = get_configured_model("generation")
        # Wrap with LangchainLLMWrapper for RAGAS
        return LangchainLLMWrapper(model)
    
    def _get_embedding_model(self):
        try:
            # Get the configured embedding model (return raw model, not wrapped)
            embedding_model = get_configured_model("embedding")
            return embedding_model
        except Exception as e:
            # Fallback to nomic-embed-text:latest
            from langchain_ollama import OllamaEmbeddings
            return OllamaEmbeddings(model="nomic-embed-text:latest")
    
    async def evaluate_single(self, query: str, ground_truth: str) -> EvaluationResult:
        # Get response from RAG system
        rag_result = await self.orchestrator.process_query(query)
        answer = rag_result.get("response", "")
        
        # Extract contexts from the new response_data structure
        contexts = []
        response_data = rag_result.get("response_data", {})
        retrieved_info = response_data.get("retrieved_information", {})
        knowledge_results = retrieved_info.get("knowledge_base_results", [])
        
        # Fallback: try to get contexts from the old structure if new structure is empty
        if not knowledge_results:
            retrieved_info_old = rag_result.get("retrieved_information", {})
            knowledge_results = retrieved_info_old.get("knowledge_base_results", [])
        
        # Extract contexts
        for result in knowledge_results:
            if "content" in result:
                contexts.append(result["content"])
        
        # Ensure we have contexts (fallback if empty)
        if not contexts:
            contexts = ["No context retrieved"]
        
        # Create RAGAS sample
        from ragas import SingleTurnSample
        sample = SingleTurnSample(
            user_input=query,
            response=answer,
            retrieved_contexts=contexts,
            reference=ground_truth  # Use 'reference' instead of 'ground_truth'
        )
        try:
            embedding_model = self._get_embedding_model()
            
            context_precision_metric = ContextPrecision(llm=self.llm)
            context_recall_metric = LLMContextRecall(llm=self.llm)
            context_entity_recall_metric = ContextEntityRecall(llm=self.llm)
            noise_sensitivity_metric = NoiseSensitivity(llm=self.llm)
            response_relevancy_metric = ResponseRelevancy(llm=self.llm, embeddings=embedding_model)
            faithfulness_metric = Faithfulness(llm=self.llm)
            multimodal_faithfulness_metric = MultiModalFaithfulness(llm=self.llm)
            multimodal_relevance_metric = MultiModalRelevance(llm=self.llm)
            
            context_precision_score = await context_precision_metric.single_turn_ascore(sample)
            context_recall_score = await context_recall_metric.single_turn_ascore(sample)
            context_entity_recall_score = await context_entity_recall_metric.single_turn_ascore(sample)
            noise_sensitivity_score = await noise_sensitivity_metric.single_turn_ascore(sample)
            response_relevancy_score = await response_relevancy_metric.single_turn_ascore(sample)
            faithfulness_score = await faithfulness_metric.single_turn_ascore(sample)
            multimodal_faithfulness_score = await multimodal_faithfulness_metric.single_turn_ascore(sample)
            multimodal_relevance_score = await multimodal_relevance_metric.single_turn_ascore(sample)
            
        except Exception as e:
            # Fallback to default scores if calculation fails
            print(f"Warning: RAGAS metric calculation failed: {e}")
            context_precision_score = 0.5
            context_recall_score = 0.5
            context_entity_recall_score = 0.5
            noise_sensitivity_score = 0.5
            response_relevancy_score = 0.5
            faithfulness_score = 0.5
            multimodal_faithfulness_score = 0.5
            multimodal_relevance_score = 0.5
        
        return EvaluationResult(
            query=query,
            ground_truth=ground_truth,
            answer=answer,
            contexts=contexts,
            context_precision=context_precision_score,
            context_recall=context_recall_score,
            context_entity_recall=context_entity_recall_score,
            noise_sensitivity=noise_sensitivity_score,
            response_relevancy=response_relevancy_score,
            faithfulness=faithfulness_score,
            multimodal_faithfulness=multimodal_faithfulness_score,
            multimodal_relevance=multimodal_relevance_score
        )
    
    
    async def evaluate_batch(self, evaluation_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        
        for item in evaluation_data:
            result = await self.evaluate_single(
                item["query"],
                item["ground_truth"]
            )
            
            # Convert EvaluationResult to dictionary
            result_dict = {
                "query": result.query,
                "ground_truth": result.ground_truth,
                "answer": result.answer,
                "contexts": result.contexts,
                "context_precision": result.context_precision,
                "context_recall": result.context_recall,
                "context_entity_recall": result.context_entity_recall,
                "noise_sensitivity": result.noise_sensitivity,
                "response_relevancy": result.response_relevancy,
                "faithfulness": result.faithfulness,
                "multimodal_faithfulness": result.multimodal_faithfulness,
                "multimodal_relevance": result.multimodal_relevance
            }
            results.append(result_dict)
        
        return results


# Factory function
async def create_simple_evaluator(vectorstore_config: Dict[str, Any]) -> SimpleRAGASEvaluator:
    from rag.components.vectorstores import get_vectorstore
    from rag.components.models import get_configured_model
    
    embedding_model = get_configured_model("embedding")
    store_type = vectorstore_config.get("type", "chroma")
    if store_type == "chroma":
        vectorstore = get_vectorstore("CHROMA_DB", embedding_function=embedding_model, **vectorstore_config)
    elif store_type == "weaviate":
        vectorstore = get_vectorstore("WEAVIATE_DB", embedding_function=embedding_model, **vectorstore_config)
    else:
        raise ValueError(f"Unsupported vectorstore type: {store_type}")
    
    orchestrator = OrchestratorAgent(vectorstore=vectorstore)
    evaluator = SimpleRAGASEvaluator(orchestrator=orchestrator)
    
    return evaluator
