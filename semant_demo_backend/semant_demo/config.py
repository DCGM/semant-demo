import os
from typing import Literal


TRUE_VALUES = {"true", "1"}

class Config():
    def __init__(self):
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")

        self.WEAVIATE_REST_PORT = os.getenv("WEAVIATE_REST_PORT", 8080)
        self.WEAVIATE_GRPC_PORT = os.getenv("WEAVIATE_GRPC_PORT", 50051)


        self.PRODUCTION = os.getenv("PRODUCTION", str(False)).lower() in TRUE_VALUES
        self.MODEL_NAME = os.getenv("MODEL_NAME", 'clip-ViT-L-14')
        self.USE_TRANSLATOR = os.getenv("USE_TRANSLATOR", str(False)).lower() in TRUE_VALUES
        self.PORT = int(os.getenv("PORT", 8002))
        self.ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:9000")

        self.GEMMA_URL = "http://localhost:8001"
        self.OLLAMA_URLS = os.getenv("OLLAMA_URLS", "http://localhost:11434").split(",")
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2") #os.getenv("OLLAMA_MODEL", "gemma3:12b")



config = Config()
