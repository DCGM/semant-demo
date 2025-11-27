from semant_demo.routes.rag_routes import BaseRag, register_rag
from semant_demo.schemas import SearchResponse, SearchRequest, SearchType, RagConfig, RagSearch, RagRouteConfig, RagRequest, RagResponse
from semant_demo.config import Config
from semant_demo.weaviate_search import WeaviateSearch
@register_rag
class TestRag(BaseRag):
    CONFIGURATION = RagRouteConfig(
        id = "testRAG",
        name="testRAG",
        description="Testovací RAG - vrací jen Router is working"
    )
    def __init__(self, config: Config, search: WeaviateSearch):
        self.config = config
        self.search = search
    async def rag_request(self, request: RagRequest) -> RagResponse:
        return RagResponse(
            rag_answer="Router is working",
            sources=[],
            time_spent=0.1
        )