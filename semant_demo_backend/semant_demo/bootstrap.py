"""Construction and release of application-scoped resources.

One ``AppResources`` instance belongs to one running application (one lifespan).
It is created at startup, stored on ``app.state.resources``, and closed at shutdown,
so the same application can be started and stopped repeatedly in one process.
"""
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from weaviate import WeaviateAsyncClient

from semant_demo.adapters.embeddings.gemma import GemmaEmbeddings
from semant_demo.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddings
from semant_demo.adapters.llm.gateway import FeatureChat, LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.adapters.llm.usage import LlmMetrics
from semant_demo.adapters.sql.quota import QuotaLedger
from semant_demo.adapters.topicer.client import TopicerClient
from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository
from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.config import Config
from semant_demo.features.analytics.service import OverviewCache
from semant_demo.features.quota.service import QuotaPolicy
from semant_demo.features.rag.registry import RagRegistry
from semant_demo.features.search.vectors import (
    Embedder, EmbeddingSettings, SearchVectors, load_search_vectors_settings,
)
from semant_demo.features.summarization.document import TemplatedDocumentSummarizer, load_document_summarizer
from semant_demo.features.summarization.templated import TemplatedSearchResultsSummarizer, load_summarizer

logger = logging.getLogger(__name__)

WeaviateConnector = Callable[[Config], Awaitable[WeaviateAsyncClient]]


@dataclass
class WeaviateRepositories:
    """Repositories sharing the application's one Weaviate client."""
    client: WeaviateAsyncClient
    documents: DocumentRepository
    tags: TagRepository
    user_collections: UserCollectionRepository
    search: ChunkSearchRepository
    spans: SpanRepository
    chunk_tags: ChunkTagRepository
    """Chunk tag re-derivation; its per-pair locks are shared by all requests of the application."""
    analytics: CorpusAnalyticsRepository

    @classmethod
    def create(cls, client: WeaviateAsyncClient, config: Config) -> "WeaviateRepositories":
        names = config.collectionNames
        return cls(
            client=client,
            documents=DocumentRepository(client, names),
            tags=TagRepository(client, names),
            user_collections=UserCollectionRepository(client, names),
            search=ChunkSearchRepository(client, names),
            spans=SpanRepository(client, names),
            chunk_tags=ChunkTagRepository(client, names),
            analytics=CorpusAnalyticsRepository(client, names),
        )


def create_embedder(settings: EmbeddingSettings, config: Config,
                    transport: httpx.AsyncBaseTransport | None = None) -> Embedder:
    """The client that embeds the queries of one search vector (``transport``: tests)."""
    if settings.provider == "embedding_service":
        return GemmaEmbeddings(settings.base_url or config.GEMMA_URL, transport=transport)
    return OpenAICompatibleEmbeddings(
        settings.base_url, settings.model, api_key=config.EMBEDDING_API_KEY, query_prefix=settings.query_prefix,
        document_prefix=settings.document_prefix, dimensions=settings.dimensions, timeout=settings.timeout,
        transport=transport)


def load_search_vectors(config: Config, transport: httpx.AsyncBaseTransport | None = None) -> SearchVectors:
    """The configured search vectors (``SEARCH_VECTORS_CONFIG``) with their embedders."""
    return SearchVectors.build(load_search_vectors_settings(config.SEARCH_VECTORS_CONFIG),
                               lambda settings: create_embedder(settings, config, transport))


@dataclass
class AppResources:
    config: Config
    engine: AsyncEngine
    session_maker: async_sessionmaker
    search_vectors: SearchVectors
    topicer: TopicerClient
    llm: LlmGateway
    span_chat: FeatureChat
    corpus_overview: OverviewCache
    quota_ledger: QuotaLedger
    quota_policy: QuotaPolicy
    rag: RagRegistry = field(default_factory=RagRegistry)
    weaviate: WeaviateRepositories | None = None
    _summarizer: TemplatedSearchResultsSummarizer | None = None
    _document_summarizer: TemplatedDocumentSummarizer | None = None

    @classmethod
    def create(cls, config: Config, llm_metrics: LlmMetrics | None = None,
               llm_transport: httpx.AsyncBaseTransport | None = None) -> "AppResources":
        """Construct resources without connecting to any external service.

        Raises ``LlmConfigurationError`` when the model tier catalog is invalid,
        ``ValidationError`` when the search vector configuration is, and ``ValueError``
        for invalid LLM quota or Topicer limit settings.
        """
        quota_policy = QuotaPolicy.from_config(config)
        llm = LlmGateway(ModelCatalog.load(config.LLM_MODELS_CONFIG), ProviderSettings.from_config(config),
                         llm_metrics, http_transport=llm_transport)
        engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        session_maker = async_sessionmaker(engine, autocommit=False, autoflush=True, expire_on_commit=False)
        return cls(config=config, engine=engine, session_maker=session_maker,
                   search_vectors=load_search_vectors(config),
                   topicer=TopicerClient(config.TOPICER_URL, config.TOPICER_CONFIG_NAME, config.TOPICER_TIMEOUT,
                                         config.TOPICER_MAX_CHUNKS_PER_TAG),
                   llm=llm,
                   span_chat=FeatureChat(llm, "span_chat", temperature=config.SPAN_CHAT_TEMPERATURE,
                                         max_tokens=config.SPAN_CHAT_MAX_TOKENS),
                   corpus_overview=OverviewCache(config.CORPUS_OVERVIEW_MAX_AGE),
                   quota_ledger=QuotaLedger(session_maker), quota_policy=quota_policy)

    async def connect_weaviate(self, connector: WeaviateConnector = connect_weaviate) -> None:
        """Open the application's Weaviate client; raises if it cannot be connected."""
        client = await connector(self.config)
        try:
            self.weaviate = WeaviateRepositories.create(client, self.config)
        except Exception:
            await client.close()
            raise

    def get_summarizer(self) -> TemplatedSearchResultsSummarizer:
        if self._summarizer is None:
            self._summarizer = load_summarizer(self.config.SEARCH_SUMMARIZER_CONFIG, self.llm)
        return self._summarizer

    def get_document_summarizer(self) -> TemplatedDocumentSummarizer:
        if self._document_summarizer is None:
            self._document_summarizer = load_document_summarizer(self.config.DOCUMENT_SUMMARIZER_CONFIG, self.llm)
        return self._document_summarizer

    async def close(self) -> None:
        """Release everything this instance opened; safe after partial startup."""
        weaviate, self.weaviate = self.weaviate, None
        self._summarizer = None
        self._document_summarizer = None
        self.rag = RagRegistry()
        try:
            if weaviate is not None:
                await weaviate.client.close()
        except Exception:
            logger.exception("Failed to close Weaviate client.")
        finally:
            # Settlements of operations whose requests were cancelled write to SQL.
            await self.llm.wait_for_settlements()
            await self.engine.dispose()
