"""RAG pipelines; importing this package registers them with the factory (``registry.py``)."""
from semant_demo.features.rag.pipelines.rag_generator import RagGenerator
from semant_demo.features.rag.pipelines.rag_test import TestRag
from semant_demo.features.rag.pipelines.agentic_rag import xmartiAgentRag
from semant_demo.features.rag.pipelines.incremental_rag import IncrementalAdaptiveRagGenerator

__all__ = ["RagGenerator", "TestRag", "xmartiAgentRag", "IncrementalAdaptiveRagGenerator"]
