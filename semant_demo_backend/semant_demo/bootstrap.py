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
from semant_demo.adapters.llm.gateway import FeatureChat, LlmGateway, ProviderSettings
from semant_demo.adapters.llm.models import ModelCatalog
from semant_demo.adapters.llm.usage import LlmMetrics
from semant_demo.adapters.topicer.client import TopicerClient
from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.config import Config
from semant_demo.rag.rag_factory import RagRegistry
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer, load_summarizer

logger = logging.getLogger(__name__)

WeaviateConnector = Callable[[Config], Awaitable[WeaviateAsyncClient]]


@dataclass
class WeaviateRepositories:
    """Repositories sharing the application's one Weaviate client."""
    client: WeaviateAsyncClient
    documents: DocumentRepository
    tags: TagRepository
    collections: UserCollectionRepository
    search: ChunkSearchRepository
    spans: SpanRepository
    chunk_tags: ChunkTagRepository
    """Chunk tag re-derivation; its per-pair locks are shared by all requests of the application."""

    @classmethod
    def create(cls, client: WeaviateAsyncClient, config: Config) -> "WeaviateRepositories":
        names = config.collectionNames
        return cls(
            client=client,
            documents=DocumentRepository(client, names),
            tags=TagRepository(client, names),
            collections=UserCollectionRepository(client, names),
            search=ChunkSearchRepository(client, names),
            spans=SpanRepository(client, names),
            chunk_tags=ChunkTagRepository(client, names),
        )


@dataclass
class AppResources:
    config: Config
    engine: AsyncEngine
    session_maker: async_sessionmaker
    embeddings: GemmaEmbeddings
    topicer: TopicerClient
    llm: LlmGateway
    span_chat: FeatureChat
    rag: RagRegistry = field(default_factory=RagRegistry)
    weaviate: WeaviateRepositories | None = None
    _summarizer: TemplatedSearchResultsSummarizer | None = None

    @classmethod
    def create(cls, config: Config, llm_metrics: LlmMetrics | None = None,
               llm_transport: httpx.AsyncBaseTransport | None = None) -> "AppResources":
        """Construct resources without connecting to any external service.

        Raises ``LlmConfigurationError`` when the model tier catalog is invalid.
        """
        llm = LlmGateway(ModelCatalog.load(config.LLM_MODELS_CONFIG), ProviderSettings.from_config(config),
                         llm_metrics, http_transport=llm_transport)
        engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        session_maker = async_sessionmaker(engine, autocommit=False, autoflush=True, expire_on_commit=False)
        return cls(config=config, engine=engine, session_maker=session_maker,
                   embeddings=GemmaEmbeddings(config.GEMMA_URL),
                   topicer=TopicerClient(config.TOPICER_URL, config.TOPICER_CONFIG_NAME, config.TOPICER_TIMEOUT),
                   llm=llm,
                   span_chat=FeatureChat(llm, "span_chat", temperature=config.SPAN_CHAT_TEMPERATURE,
                                         max_tokens=config.SPAN_CHAT_MAX_TOKENS))

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

    async def close(self) -> None:
        """Release everything this instance opened; safe after partial startup."""
        weaviate, self.weaviate = self.weaviate, None
        self._summarizer = None
        self.rag = RagRegistry()
        try:
            if weaviate is not None:
                await weaviate.client.close()
        except Exception:
            logger.exception("Failed to close Weaviate client.")
        finally:
            await self.engine.dispose()
