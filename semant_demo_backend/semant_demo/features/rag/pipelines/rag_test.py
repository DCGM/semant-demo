from semant_demo.features.rag.registry import BaseRag, register_rag_class
from semant_demo.features.rag.schemas import RagRequest, RagResponse
from semant_demo.config import Config
from semant_demo.features.search.service import Retriever
@register_rag_class
class TestRag(BaseRag):
    def __init__(self, global_config: Config, param_config, llm=None):
        super().__init__(global_config, param_config, llm)
        self.retrieve = None
    async def rag_request(self, request: RagRequest, retrieve: Retriever) -> RagResponse:
        self.retrieve = retrieve
        return RagResponse(
            rag_answer="Router is working",
            sources=[],
            time_spent=0.1,
            response_id="test"
        )