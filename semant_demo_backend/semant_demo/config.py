import json
import os
from pathlib import Path
from semant_demo.schemas import CollectionNames, EmbeddingProvider


TRUE_VALUES = {"true", "1"}
SCRIPT_PATH = Path(__file__).parent
DEFAULT_CHUNK_VECTORS = [
    "nomic_embed_text_v2_moe",
    "qwen3_embedding_4b",
    "qwen3_embedding_0_6b",
]

class Config:
    def __init__(self):
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://openrouter.ai/api/v1")
        self.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", self.OPENAI_API_KEY)
        self.OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL", self.OPENAI_API_URL)
        
        self.WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
        self.WEAVIATE_REST_PORT = os.getenv("WEAVIATE_REST_PORT", 8080)
        self.WEAVIATE_GRPC_PORT = os.getenv("WEAVIATE_GRPC_PORT", 50051)

        embedding_service_host = os.getenv("EMBEDDING_SERVICE_HOST","embedding-service")
        embedding_service_port = os.getenv("EMBEDDING_SERVICE_PORT",8001)
        self.GEMMA_URL = f"http://{embedding_service_host}:{embedding_service_port}"
        #self.GEMMA_URL = "http://localhost:8001"

        self.PRODUCTION = os.getenv("PRODUCTION", str(False)).lower() in TRUE_VALUES
        self.MODEL_NAME = os.getenv("MODEL_NAME", 'clip-ViT-L-14')
        self.USE_TRANSLATOR = os.getenv("USE_TRANSLATOR", str(False)).lower() in TRUE_VALUES
        self.PORT = int(os.getenv("PORT", 8000))
        self.STATIC_PATH = os.getenv("STATIC_PATH", "./static")
        self.ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:9000")

        self.OLLAMA_URLS = os.getenv("OLLAMA_URLS", "http://localhost:11434").split(",")
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:12b")
        self.SEARCH_SUMMARIZER_CONFIG = os.getenv("SEARCH_SUMMARIZER_CONFIG", str(SCRIPT_PATH / "configs" / "search_summarizer.yaml"))

        self.AVAILABLE_CHUNK_VECTORS = os.getenv(
            "AVAILABLE_CHUNK_VECTORS",
            ",".join(DEFAULT_CHUNK_VECTORS),
        )
        self.AVAILABLE_CHUNK_VECTORS = [
            vector_name.strip()
            for vector_name in self.AVAILABLE_CHUNK_VECTORS.split(",")
            if vector_name.strip()
        ]
        self.DEFAULT_CHUNK_VECTOR = os.getenv("DEFAULT_CHUNK_VECTOR", "nomic_embed_text_v2_moe")
        self.CHUNK_VECTOR_EMBEDDINGS = self._load_chunk_vector_embeddings()
        self.validate_chunk_vector(self.DEFAULT_CHUNK_VECTOR)

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
        
        # path to rag configs
        default_config_path = SCRIPT_PATH / "rag" / "rag_configs" / "demo_configs"
        test_configs_path = SCRIPT_PATH / "rag" / "rag_configs" / "tests"
        self.RAG_CONFIGS_PATH = os.getenv("RAG_CONFIGS_PATH", default_config_path)

        self.collectionNames = CollectionNames(
            chunks_collection_name = os.getenv("CHUNKS_COLLECTION_NAME", "Chunks_test_multivector"),
            tag_collection_name = "Tag",
            user_collection_name = "UserCollection",
            document_collection_name= "Documents",
            span_collection_name = "Span_test",
            user_collection_link_name = "userCollection",
            tag_to_user_collection_link_name= "tagToUserCollection",
        )

    def _load_chunk_vector_embeddings(self) -> dict[str, dict[str, str]]:
        default_mapping = {
            "nomic_embed_text_v2_moe": {
                "provider": EmbeddingProvider.ollama.value,
                "model": os.getenv("OLLAMA_NOMIC_EMBEDDING_MODEL", "nomic-embed-text:v2-moe"),
                "base_url": self.OLLAMA_URLS[0],
            },
            "qwen3_embedding_4b": {
                "provider": EmbeddingProvider.openrouter.value,
                "model": os.getenv("OPENROUTER_QWEN3_EMBEDDING_4B_MODEL", "qwen/qwen3-embedding-4b"),
                "base_url": self.OPENROUTER_API_URL,
                "api_key": self.OPENROUTER_API_KEY,
            },
            "qwen3_embedding_0_6b": {
                "provider": EmbeddingProvider.openrouter.value,
                "model": os.getenv("OPENROUTER_QWEN3_EMBEDDING_0_6B_MODEL", "qwen/qwen3-embedding-0.6b"),
                "base_url": self.OPENROUTER_API_URL,
                "api_key": self.OPENROUTER_API_KEY,
            },
        }

        raw_mapping = os.getenv("CHUNK_VECTOR_EMBEDDINGS")
        if raw_mapping is None:
            return default_mapping

        configured_mapping = json.loads(raw_mapping)
        return {**default_mapping, **configured_mapping}

    def validate_chunk_vector(self, vector_name: str) -> str:
        if vector_name not in self.AVAILABLE_CHUNK_VECTORS:
            raise ValueError(
                f"Unknown chunk vector '{vector_name}'. "
                f"Available vectors: {', '.join(self.AVAILABLE_CHUNK_VECTORS)}"
            )
        if vector_name not in self.CHUNK_VECTOR_EMBEDDINGS:
            raise ValueError(f"Missing embedding configuration for chunk vector '{vector_name}'")
        return vector_name

    def resolve_chunk_vector(self, vector_name: str | None = None) -> str:
        return self.validate_chunk_vector(vector_name or self.DEFAULT_CHUNK_VECTOR)

    def get_chunk_vector_embedding_config(self, vector_name: str | None = None) -> dict[str, str]:
        resolved_vector = self.resolve_chunk_vector(vector_name)
        return self.CHUNK_VECTOR_EMBEDDINGS[resolved_vector]

config = Config()
