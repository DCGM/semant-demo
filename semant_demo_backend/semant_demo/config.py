import os
from pathlib import Path


TRUE_VALUES = {"true", "1"}
SCRIPT_PATH = Path(__file__).parent

class Config:
    def __init__(self):
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://openrouter.ai/api/v1")
        
        self.WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
        self.WEAVIATE_REST_PORT = os.getenv("WEAVIATE_REST_PORT", 8080)
        self.WEAVIATE_GRPC_PORT = os.getenv("WEAVIATE_GRPC_PORT", 50051)

        embedding_service_host = os.getenv("EMBEDDING_SERVICE_HOST","embedding-service")
        embedding_service_port = os.getenv("EMBEDDING_SERVICE_PORT",8001)
        self.GEMMA_URL = f"http://{embedding_service_host}:{embedding_service_port}"

        self.PRODUCTION = os.getenv("PRODUCTION", str(False)).lower() in TRUE_VALUES
        self.MODEL_NAME = os.getenv("MODEL_NAME", 'clip-ViT-L-14')
        self.USE_TRANSLATOR = os.getenv("USE_TRANSLATOR", str(False)).lower() in TRUE_VALUES
        self.PORT = int(os.getenv("PORT", 8000))
        self.STATIC_PATH = os.getenv("STATIC_PATH", "./static")
        self.ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:9000")

        self.OLLAMA_URLS = os.getenv("OLLAMA_URLS", "http://localhost:11434").split(",")
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")
        self.SEARCH_SUMMARIZER_CONFIG = os.getenv("SEARCH_SUMMARIZER_CONFIG", str(SCRIPT_PATH / "configs" / "search_summarizer.yaml"))

        self.GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-pro")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
        self.LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")

        self.MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", 0.0))

        # SQL db
        self.SQL_DB_URL = "sqlite+aiosqlite:///tasks.db"
        
        # path to rag configs
        default_config_path = SCRIPT_PATH / "rag" / "rag_configs" / "demo_configs"
        test_configs_path = SCRIPT_PATH / "rag" / "rag_configs" / "tests"
        self.RAG_CONFIGS_PATH = os.getenv("RAG_CONFIGS_PATH", default_config_path)

config = Config()
