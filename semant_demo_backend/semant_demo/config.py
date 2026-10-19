import os
from pathlib import Path
from typing import Mapping
from semant_demo.adapters.weaviate.names import CollectionNames


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
        # Search vectors: Weaviate named vectors and their query embedding (features/search/vectors.py).
        self.SEARCH_VECTORS_CONFIG = env.get("SEARCH_VECTORS_CONFIG", str(SCRIPT_PATH / "configs" / "search_vectors.yaml"))
        # Contextual vector of span annotations (#328, features/annotations/enrichment.py); empty: none.
        self.ANNOTATION_VECTOR_CONFIG = env.get("ANNOTATION_VECTOR_CONFIG",
                                                str(SCRIPT_PATH / "configs" / "annotation_vector.yaml"))
        # Bearer key of the OpenAI-compatible embedding endpoints of search vectors; empty sends none.
        self.EMBEDDING_API_KEY = env.get("EMBEDDING_API_KEY", "")

        self.PRODUCTION = env.get("PRODUCTION", str(False)).lower() in TRUE_VALUES
        self.PORT = int(env.get("PORT", 8000))
        self.STATIC_PATH = env.get("STATIC_PATH", "./static")
        self.ALLOWED_ORIGIN = env.get("ALLOWED_ORIGIN", "http://localhost:9000")
        self.LOG_LEVEL = env.get("LOG_LEVEL", "INFO").upper()

        # Only the first URL is used: the default endpoint of Ollama model tiers.
        self.OLLAMA_URLS = env.get("OLLAMA_URLS", "http://localhost:11434").split(",")
        self.SEARCH_SUMMARIZER_CONFIG = env.get("SEARCH_SUMMARIZER_CONFIG", str(SCRIPT_PATH / "configs" / "search_summarizer.yaml"))
        self.DOCUMENT_SUMMARIZER_CONFIG = env.get("DOCUMENT_SUMMARIZER_CONFIG", str(SCRIPT_PATH / "configs" / "document_summarizer.yaml"))
        self.SEARCH_FILTERS_CONFIG = env.get("SEARCH_FILTERS_CONFIG", str(SCRIPT_PATH / "configs" / "search_filters.yaml"))

        self.GOOGLE_API_KEY = env.get("GOOGLE_API_KEY", "")

        # Server-side model tiers and the tiers each feature may use (adapters/llm/models.py).
        self.LLM_MODELS_CONFIG = env.get("LLM_MODELS_CONFIG", str(SCRIPT_PATH / "configs" / "llm_models.yaml"))
        # Timeout (seconds) and SDK retries of one provider request of the LLM gateway.
        self.LLM_TIMEOUT_SECONDS = float(env.get("LLM_TIMEOUT_SECONDS", 120.0))
        self.LLM_MAX_RETRIES = int(env.get("LLM_MAX_RETRIES", 1))
        # Most recent RAG history messages sent to the model; older ones are left out.
        self.RAG_HISTORY_LIMIT = int(env.get("RAG_HISTORY_LIMIT", 20))

        # Daily LLM allowances (features/quota): USD-equivalent estimates per UTC calendar day,
        # separately for guests (anonymous cookie) and signed-in accounts. Not a bill.
        self.LLM_QUOTA_GUEST_DAILY_USD = float(env.get("LLM_QUOTA_GUEST_DAILY_USD", 0.25))
        self.LLM_QUOTA_ACCOUNT_DAILY_USD = float(env.get("LLM_QUOTA_ACCOUNT_DAILY_USD", 1.00))
        # Share of the allowance used from which the quota status reports near_limit.
        self.LLM_QUOTA_NEAR_LIMIT_RATIO = float(env.get("LLM_QUOTA_NEAR_LIMIT_RATIO", 0.8))
        # Lifetime of the guest identity cookie; clearing the cookie starts a new guest allowance.
        self.LLM_QUOTA_GUEST_COOKIE_DAYS = int(env.get("LLM_QUOTA_GUEST_COOKIE_DAYS", 30))
        # Send the guest cookie only over HTTPS; default: whether ALLOWED_ORIGIN is https.
        secure = env.get("LLM_QUOTA_GUEST_COOKIE_SECURE")
        self.LLM_QUOTA_GUEST_COOKIE_SECURE = (self.ALLOWED_ORIGIN.lower().startswith("https://") if secure is None
                                              else secure.lower() in TRUE_VALUES)

        # SQL db
        # Default is relative to the backend working directory.
        self.SQL_DB_URL = env.get("SQL_DB_URL", "sqlite+aiosqlite:///tasks.db")

        # app feedback delivery
        self.FEEDBACK_WEBHOOK_URL = env.get("FEEDBACK_WEBHOOK_URL", "")
        # An empty value (as in the deploy .env templates) means the default path.
        self.FEEDBACK_LOG_PATH = env.get("FEEDBACK_LOG_PATH") or str(SCRIPT_PATH / "feedback.log.jsonl")

        # Auth – override JWT_SECRET in production with a strong random value
        self.JWT_SECRET = env.get("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET")
        
        # Topicer (AI assistance / tag proposal service)
        self.TOPICER_URL = env.get("TOPICER_URL", "http://topicer:8089")
        self.TOPICER_CONFIG_NAME = env.get("TOPICER_CONFIG_NAME", "openai")
        self.TOPICER_TIMEOUT = float(env.get("TOPICER_TIMEOUT", 600.0))
        # Most chunks one optimized suggestion stream evaluates per tag, sent to Topicer as
        # max_chunks (semANT's policy; must not exceed Topicer's own max_chunks_ceiling).
        self.TOPICER_MAX_CHUNKS_PER_TAG = int(env.get("TOPICER_MAX_CHUNKS_PER_TAG", 40))
        # Daily-allowance reservation (USD-equivalent) for one Topicer chunk evaluation: a
        # thorough chunk or a selection chunk; an optimized tag reserves it per allowed chunk.
        self.TOPICER_RESERVE_USD_PER_CHUNK = float(env.get("TOPICER_RESERVE_USD_PER_CHUNK", 0.005))

        # Annotation tenants (#327): the backend records when each collection's annotation
        # tenant was last used (at most once per this many seconds per process; long
        # operations repeat it), so that ``maintenance.annotation_tenants`` deactivates
        # only idle tenants. Deactivation stays off until it is enabled explicitly
        # (after the active/inactive backup and restore rehearsal, docs/DATA_MAINTENANCE.md).
        self.ANNOTATION_TENANT_TOUCH_SECONDS = float(env.get("ANNOTATION_TENANT_TOUCH_SECONDS", 60.0))
        self.ANNOTATION_TENANT_IDLE_SECONDS = float(env.get("ANNOTATION_TENANT_IDLE_SECONDS", 3600.0))
        self.ANNOTATION_TENANT_DEACTIVATION_ENABLED = (
            env.get("ANNOTATION_TENANT_DEACTIVATION_ENABLED", str(False)).lower() in TRUE_VALUES)

        # Span discussion chat; its model is the span_chat feature's tier (LLM_MODELS_CONFIG).
        self.SPAN_CHAT_TEMPERATURE = float(env.get("SPAN_CHAT_TEMPERATURE", 0.4))
        self.SPAN_CHAT_MAX_TOKENS = int(env.get("SPAN_CHAT_MAX_TOKENS", 1024))
        # Number of characters of surrounding chunk text to include before/after
        # the span when building the assistant context.
        self.SPAN_CHAT_CONTEXT_CHARS = int(env.get("SPAN_CHAT_CONTEXT_CHARS", 1500))
        # Cap on the number of user/assistant messages kept from history
        # (system + context + last N exchanges).
        self.SPAN_CHAT_HISTORY_LIMIT = int(env.get("SPAN_CHAT_HISTORY_LIMIT", 20))

        # Corpus overview (#254): seconds a computed overview is served before it is computed again.
        self.CORPUS_OVERVIEW_MAX_AGE = float(env.get("CORPUS_OVERVIEW_MAX_AGE", 600.0))

        # path to rag configs
        default_config_path = SCRIPT_PATH / "configs" / "rag" / "demo_configs"
        self.RAG_CONFIGS_PATH = env.get("RAG_CONFIGS_PATH", str(default_config_path))

        # OpenTelemetry - disabled by default so local/test runs never try to reach a collector
        self.OTEL_ENABLED = env.get("OTEL_ENABLED", str(False)).lower() in TRUE_VALUES
        self.OTEL_EXPORTER_OTLP_ENDPOINT = env.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4318")
        self.OTEL_EXPORTER_OTLP_LOGS_PATH = env.get("OTEL_EXPORTER_OTLP_LOGS_PATH", "/v1/logs")
        self.OTEL_EXPORTER_OTLP_TRACES_PATH = env.get("OTEL_EXPORTER_OTLP_TRACES_PATH", "/v1/traces")
        self.OTEL_EXPORTER_OTLP_METRICS_PATH = env.get("OTEL_EXPORTER_OTLP_METRICS_PATH", "/v1/metrics")
        self.OTEL_METRIC_EXPORT_INTERVAL_MS = int(env.get("OTEL_METRIC_EXPORT_INTERVAL_MS", 10000))
        self.OTEL_SERVICE_NAME = env.get("OTEL_SERVICE_NAME", "semant-demo-backend")
        self.DEPLOYMENT_ENVIRONMENT = env.get("DEPLOYMENT_ENVIRONMENT", "unknown")

        self.collectionNames = CollectionNames(
            chunks_collection_name = "Chunks",
            tag_collection_name = "Tag",
            user_collection_name = "UserCollection",
            document_collection_name= "Documents",
            span_collection_name = "Span",
            annotation_collection_name = "Annotation",
            user_collection_link_name = "userCollection",
            tag_to_user_collection_link_name= "tagToUserCollection",
        )

config = Config()
