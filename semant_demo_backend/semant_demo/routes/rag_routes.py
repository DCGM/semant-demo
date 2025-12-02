from typing import Dict, Type
from semant_demo.schemas import RagRouteConfig, RagRequest, RagResponse

class BaseRag:
   CONFIGURATION: RagRouteConfig = None 
   
   async def rag_request(self, request: RagRequest) -> RagResponse:
        raise NotImplementedError("Method \"rag_request\" is not implemented.")

#dict of rag implementations avalaible in application    
RAG_IMPLEMENTATIONS: Dict[str, Type[BaseRag]] = {}

#rag registration
def register_rag(rag_class: Type[BaseRag]):
    RAG_IMPLEMENTATIONS[rag_class.CONFIGURATION.id] = rag_class

#return all avalaible rag configurations registered in app
def get_all_rag_configurations() -> list[RagRouteConfig]:
    all_configs = []
    for rag_class in RAG_IMPLEMENTATIONS.values():
        all_configs.append(rag_class.CONFIGURATION)
    return all_configs
