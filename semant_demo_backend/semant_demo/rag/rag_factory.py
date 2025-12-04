import os
import yaml
import logging
from typing import Dict, Type
from semant_demo.schemas import RagRouteConfig, RagRequest, RagResponse

class BaseRag:
   def __init__(self, global_config, param_config):
       self.global_config = global_config
       self.param_config = param_config
       
   async def rag_request(self, request: RagRequest, searcher) -> RagResponse:
        raise NotImplementedError("Method \"rag_request\" is not implemented.")

#dict of rag implementations avalaible in application    
RAG_IMPLEMENTATIONS: Dict[str, Type[BaseRag]] = {}

#rag class registration
def register_rag_class(rag_class: Type[BaseRag]):
    RAG_IMPLEMENTATIONS[rag_class.__name__] = rag_class
    return rag_class

#rag dict of particular configurations
#for backend
RAG_INSTANCES: Dict[str, BaseRag] = {}
#for frontend
RAG_INSTANCES_CONFIGS: Dict[str, RagRouteConfig] = {}

def rag_factory(global_config, configs_path: str):
    RAG_INSTANCES.clear()
    RAG_INSTANCES_CONFIGS.clear()
    
    if not os.path.exists(configs_path):
        logging.error(f"RAG configs directory was not found: {configs_path}.")
        return
    
    for filename in os.listdir(configs_path):
        if filename.endswith(".yaml"):
            filepath = os.path.join(configs_path, filename)
            try:
                #load rag config
                with open (filepath, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                
                id = config.get("id")
                name = config.get("name")
                desc = config.get("description")
                class_name = config.get("class_name")
                params = config.get("params", {})
                
                if (not id or not name or not desc or not class_name or not params):
                    logging.error(f"Yaml is in wrong format, skipping configuration: {filename}.")
                    continue
                if (class_name not in RAG_IMPLEMENTATIONS):
                    logging.error(f"Unknown class: {class_name}, skipping configuration: {filename}.")
                    continue
                if (id in RAG_INSTANCES_CONFIGS):
                    logging.error(f"Same configuration id: {id}, skipping configuration: {filename}.")
                    continue
                
                #get class of choice
                RagClass = RAG_IMPLEMENTATIONS[class_name]
                
                #create an instance
                instance = RagClass(global_config=global_config, param_config=params)
                RAG_INSTANCES[id] = instance
                
                #create frontend config
                frontend_config = RagRouteConfig(id=id, name=name, description=desc)
                RAG_INSTANCES_CONFIGS[id] = frontend_config
                
            except Exception as e:
                logging.error(f"Failed to load RAG configuration: {filename}: {e}")
    
    

#return all avalaible rag configurations registered in app
def get_all_rag_configurations() -> list[RagRouteConfig]:
    return list(RAG_INSTANCES_CONFIGS.values())
