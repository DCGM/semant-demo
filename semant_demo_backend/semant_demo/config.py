import os
from pathlib import Path
from typing import Mapping
from semant_demo.schemas import CollectionNames


TRUE_VALUES = {"true", "1"}
SCRIPT_PATH = Path(__file__).parent

class Config:
    """Application settings.

    Values are read once, at construction, from ``environ`` (``os.environ`` when
    omitted). Pass an explicit mapping to build isolated settings, e.g. in tests;
    such a ``Config`` does not see the process environment at all.
    """

    def __init__(self, environ: Mapping[str, str] | None = None):
        env = os.environ if environ is None else environ
        self.OPENAI_API_KEY = env.get("OPENAI_API_KEY", "")
        self.OPENAI_API_URL = env.get("OPENAI_API_URL", "https://openrouter.ai/api/v1")

        self.WEAVIATE_HOST = env.get("WEAVIATE_HOST", "localhost")
        self.WEAVIATE_REST_PORT = int(env.get("WEAVIATE_REST_PORT", 8080))
        self.WEAVIATE_GRPC_PORT = int(env.get("WEAVIATE_GRPC_PORT", 50051))

        embedding_service_host = env.get("EMBEDDING_SERVICE_HOST","embedding-service")
        embedding_service_port = env.get("EMBEDDING_SERVICE_PORT",8001)
        self.GEMMA_URL = f"http://{embedding_service_host}:{embedding_service_port}"
        #self.GEMMA_URL = "http://localhost:8001"

        self.PRODUCTION = env.get("PRODUCTION", str(False)).lower() in TRUE_VALUES
        self.PORT = int(env.get("PORT", 8000))
        self.STATIC_PATH = env.get("STATIC_PATH", "./static")
        self.ALLOWED_ORIGIN = env.get("ALLOWED_ORIGIN", "http://localhost:9000")

        self.OLLAMA_URLS = env.get("OLLAMA_URLS", "http://localhost:11434").split(",")
        self.OLLAMA_MODEL = env.get("OLLAMA_MODEL", "gemma3:12b")
        self.SEARCH_SUMMARIZER_CONFIG = env.get("SEARCH_SUMMARIZER_CONFIG", str(SCRIPT_PATH / "configs" / "search_summarizer.yaml"))
        self.SEARCH_FILTERS_CONFIG = env.get("SEARCH_FILTERS_CONFIG", str(SCRIPT_PATH / "configs" / "search_filters.yaml"))

        self.GOOGLE_MODEL = env.get("GOOGLE_MODEL", "gemini-2.5-pro")
        self.OPENAI_MODEL = env.get("OPENAI_MODEL", "gpt-4o-mini")

        self.GOOGLE_API_KEY = env.get("GOOGLE_API_KEY", "")
        self.LANGCHAIN_API_KEY = env.get("LANGCHAIN_API_KEY", "")

        self.MODEL_TEMPERATURE = float(env.get("MODEL_TEMPERATURE", 0.0))

        # SQL db
        # Default is relative to the backend working directory.
        self.SQL_DB_URL = env.get("SQL_DB_URL", "sqlite+aiosqlite:///tasks.db")

        # app feedback delivery
        self.FEEDBACK_WEBHOOK_URL = env.get("FEEDBACK_WEBHOOK_URL", "")
        self.FEEDBACK_LOG_PATH = env.get("FEEDBACK_LOG_PATH", str(SCRIPT_PATH / "feedback.log.jsonl"))

        # Auth – override JWT_SECRET in production with a strong random value
        self.JWT_SECRET = env.get("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET")
        
        # Topicer (AI assistance / tag proposal service)
        self.TOPICER_URL = env.get("TOPICER_URL", "http://topicer:8089")
        self.TOPICER_CONFIG_NAME = env.get("TOPICER_CONFIG_NAME", "openai")
        self.TOPICER_TIMEOUT = float(env.get("TOPICER_TIMEOUT", 600.0))

        # Span discussion chat (OpenAI-compatible endpoint).
        # Defaults reuse the generic OPENAI_* settings so a single API key
        # can drive both generic LLM use and the span chat unless overridden.
        self.SPAN_CHAT_API_KEY = env.get("SPAN_CHAT_API_KEY", self.OPENAI_API_KEY)
        self.SPAN_CHAT_API_URL = env.get("SPAN_CHAT_API_URL", self.OPENAI_API_URL)
        self.SPAN_CHAT_MODEL = env.get("SPAN_CHAT_MODEL", self.OPENAI_MODEL)
        self.SPAN_CHAT_TEMPERATURE = float(env.get("SPAN_CHAT_TEMPERATURE", 0.4))
        self.SPAN_CHAT_MAX_TOKENS = int(env.get("SPAN_CHAT_MAX_TOKENS", 1024))
        # Number of characters of surrounding chunk text to include before/after
        # the span when building the assistant context.
        self.SPAN_CHAT_CONTEXT_CHARS = int(env.get("SPAN_CHAT_CONTEXT_CHARS", 1500))
        # Cap on the number of user/assistant messages kept from history
        # (system + context + last N exchanges).
        self.SPAN_CHAT_HISTORY_LIMIT = int(env.get("SPAN_CHAT_HISTORY_LIMIT", 20))

        # path to rag configs
        default_config_path = SCRIPT_PATH / "rag" / "rag_configs" / "demo_configs"
        self.RAG_CONFIGS_PATH = env.get("RAG_CONFIGS_PATH", str(default_config_path))

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
