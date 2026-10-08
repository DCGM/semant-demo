from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.schemas import RagRequest, RagResponse
from semant_demo.config import Config
from semant_demo.features.search.service import Retriever
@register_rag_class
class TestRag(BaseRag):
    def __init__(self, global_config: Config, param_config):
        super().__init__(global_config, param_config)
        self.retrieve = None
        #get params from config
        self.model_type = param_config.get("model_type")
    async def rag_request(self, request: RagRequest, retrieve: Retriever) -> RagResponse:
        self.retrieve = retrieve
        return RagResponse(
            rag_answer="Router is working",
            sources=[],
            time_spent=0.1
        )