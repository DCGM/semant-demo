from semant_demo.rag.rag_factory import BaseRag, register_rag_class
from semant_demo.schemas import SearchResponse, SearchRequest, SearchType, RagConfig, RagSearch, RagRouteConfig, RagRequest, RagResponse
from semant_demo.config import Config
from semant_demo.weaviate_search import WeaviateSearch
@register_rag_class
class TestRag(BaseRag):
    def __init__(self, global_config: Config, param_config, searcher: WeaviateSearch):
        super().__init__(global_config, param_config, searcher)
        #get params from config
        self.model_type = param_config.get("model_type")
    async def rag_request(self, request: RagRequest) -> RagResponse:
        return RagResponse(
            rag_answer="Router is working",
            sources=[],
            time_spent=0.1
        )