import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import Dict, Type
from semant_demo.schemas import RagRouteConfig, RagRequest, RagResponse, ExplainRequest

class BaseRag:
   def __init__(self, global_config, param_config):
       self.global_config = global_config
       self.param_config = param_config
       
   async def rag_request(self, request: RagRequest, retrieve) -> RagResponse:
        raise NotImplementedError("Method \"rag_request\" is not implemented.")
   
   async def explain_selection(self, request : ExplainRequest):
       return {"explanation" : "This functionality is not supported by this RAG, try another."}

#dict of rag implementations avalaible in application    
RAG_IMPLEMENTATIONS: Dict[str, Type[BaseRag]] = {}

#rag class registration
def register_rag_class(rag_class: Type[BaseRag]):
    RAG_IMPLEMENTATIONS[rag_class.__name__] = rag_class
    return rag_class

#configured rag instances of one application
@dataclass
class RagRegistry:
    #for backend
    instances: Dict[str, BaseRag] = field(default_factory=dict)
    #for frontend
    configs: Dict[str, RagRouteConfig] = field(default_factory=dict)

    #return all avalaible rag configurations registered in app
    def get_all_configurations(self) -> list[RagRouteConfig]:
        return list(self.configs.values())

#load single rag configuration and return  id and frontend_config, instance of the class
def rag_load_single_config(global_config, filepath: str):
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
            logging.error(f"Yaml is in wrong format, skipping configuration: {filepath}.")
            return None
        if (class_name not in RAG_IMPLEMENTATIONS):
            logging.error(f"Unknown class: {class_name}, skipping configuration: {filepath}.")
            return None

        
        #get class of choice
        RagClass = RAG_IMPLEMENTATIONS[class_name]
        
        #create an instance
        instance = RagClass(global_config=global_config, param_config=params)
        
        #create frontend config
        frontend_config = RagRouteConfig(id=id, name=name, description=desc)

        return id, frontend_config, instance
        
    except Exception as e:
        logging.error(f"Failed to load RAG configuration: {filepath}: {e}")

def rag_factory(global_config, configs_path: str) -> RagRegistry:
    registry = RagRegistry()

    if not os.path.exists(configs_path):
        logging.error(f"RAG configs directory was not found: {configs_path}.")
        return registry
    
    for filename in os.listdir(configs_path):
        if filename.endswith(".yaml"):
            filepath = os.path.join(configs_path, filename)

            #load single config
            results = rag_load_single_config(global_config=global_config, filepath=filepath)

            if (results is None):
                continue

            id, frontend_config, instance = results

            #duplicity check
            if (id in registry.configs):
                logging.error(f"Same configuration id: {id}, skipping configuration: {filepath}.")
                continue
                
            #create an instance
            registry.instances[id] = instance
            
            #create frontend config
            registry.configs[id] = frontend_config

    return registry
