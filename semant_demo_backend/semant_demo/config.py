import os
from pathlib import Path
from semant_demo.schemas import CollectionNames


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
        #self.GEMMA_URL = "http://localhost:8001"

        self.TOPICER_URL = os.getenv("TOPICER_URL", "http://localhost:8089")
        self.TOPICER_CONFIG_NAME = os.getenv("TOPICER_CONFIG_NAME", "")
        self.TOPICER_TIMEOUT = float(os.getenv("TOPICER_TIMEOUT", 30.0))
        self.TOPICER_READ_WRITE_TIMEOUT = float(os.getenv("TOPICER_RW_TIMEOUT", 600.0))

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

        # app feedback delivery
        self.FEEDBACK_WEBHOOK_URL = os.getenv("FEEDBACK_WEBHOOK_URL", "")
        self.FEEDBACK_LOG_PATH = os.getenv("FEEDBACK_LOG_PATH", str(SCRIPT_PATH / "feedback.log.jsonl"))

        # Auth – override JWT_SECRET in production with a strong random value
        self.JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET")
        
        # Topicer (AI assistance / tag proposal service)
        self.TOPICER_URL = os.getenv("TOPICER_URL", "http://topicer:8089")
        self.TOPICER_CONFIG_NAME = os.getenv("TOPICER_CONFIG_NAME", "openai")
        self.TOPICER_TIMEOUT = float(os.getenv("TOPICER_TIMEOUT", 600.0))

        # Span discussion chat (OpenAI-compatible endpoint).
        # Defaults reuse the generic OPENAI_* settings so a single API key
        # can drive both generic LLM use and the span chat unless overridden.
        self.SPAN_CHAT_API_KEY = os.getenv("SPAN_CHAT_API_KEY", self.OPENAI_API_KEY)
        self.SPAN_CHAT_API_URL = os.getenv("SPAN_CHAT_API_URL", self.OPENAI_API_URL)
        self.SPAN_CHAT_MODEL = os.getenv("SPAN_CHAT_MODEL", self.OPENAI_MODEL)
        self.SPAN_CHAT_TEMPERATURE = float(os.getenv("SPAN_CHAT_TEMPERATURE", 0.4))
        self.SPAN_CHAT_MAX_TOKENS = int(os.getenv("SPAN_CHAT_MAX_TOKENS", 1024))
        # Number of characters of surrounding chunk text to include before/after
        # the span when building the assistant context.
        self.SPAN_CHAT_CONTEXT_CHARS = int(os.getenv("SPAN_CHAT_CONTEXT_CHARS", 1500))
        # Cap on the number of user/assistant messages kept from history
        # (system + context + last N exchanges).
        self.SPAN_CHAT_HISTORY_LIMIT = int(os.getenv("SPAN_CHAT_HISTORY_LIMIT", 20))

        # path to rag configs
        default_config_path = SCRIPT_PATH / "rag" / "rag_configs" / "demo_configs"
        test_configs_path = SCRIPT_PATH / "rag" / "rag_configs" / "tests"
        self.RAG_CONFIGS_PATH = os.getenv("RAG_CONFIGS_PATH", default_config_path)

        self.collectionNames = CollectionNames(
            chunks_collection_name = "Chunks",
            tag_collection_name = "Tag",
            user_collection_name = "UserCollection",
            document_collection_name= "Documents",
            span_collection_name = "Span",
            user_collection_link_name = "userCollection",
            tag_to_user_collection_link_name= "tagToUserCollection",
        )

config = Config()
