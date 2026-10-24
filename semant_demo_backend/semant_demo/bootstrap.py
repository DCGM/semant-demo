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
from semant_demo.adapters.sql.attributes import AttributeRepository
from semant_demo.adapters.sql.quota import QuotaLedger
from semant_demo.adapters.sql.tenant_activity import TenantActivity
from semant_demo.adapters.topicer.client import TopicerClient
from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository
from semant_demo.adapters.weaviate.chunk_tags import ChunkTagRepository
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository, missing_position_properties
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.adapters.weaviate.spans import SpanRepository, attribute_schema, enrichment_schema, provenance_schema
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.config import Config
from semant_demo.features.analytics.service import OverviewCache
from semant_demo.features.annotations.enrichment import AnnotationVector, Enrichment, load_annotation_vector_settings
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
    """Annotation spans, one tenant per user collection (#327); its known-tenant cache is per application."""
    chunk_tags: ChunkTagRepository
    """Chunk tag re-derivation; its per-pair locks are shared by all requests of the application."""
    analytics: CorpusAnalyticsRepository

    @classmethod
    def create(cls, client: WeaviateAsyncClient, config: Config) -> "WeaviateRepositories":
        names = config.collectionNames
        spans = SpanRepository(client, names)
        return cls(
            client=client,
            documents=DocumentRepository(client, names),
            tags=TagRepository(client, names, spans),
            user_collections=UserCollectionRepository(client, names, spans),
            search=ChunkSearchRepository(client, names),
            spans=spans,
            chunk_tags=ChunkTagRepository(client, names, spans),
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


def load_annotation_vector(config: Config, transport: httpx.AsyncBaseTransport | None = None
                           ) -> AnnotationVector | None:
    """The configured contextual annotation vector (``ANNOTATION_VECTOR_CONFIG``) with its embedder."""
    settings = load_annotation_vector_settings(config.ANNOTATION_VECTOR_CONFIG)
    if settings is None:
        return None
    return AnnotationVector(settings, create_embedder(settings.embedding, config, transport))


def load_search_vectors(config: Config, transport: httpx.AsyncBaseTransport | None = None) -> SearchVectors:
    """The configured search vectors (``SEARCH_VECTORS_CONFIG``) with their embedders."""
    return SearchVectors.build(load_search_vectors_settings(config.SEARCH_VECTORS_CONFIG),
                               lambda settings: create_embedder(settings, config, transport))


async def detect_enrichment(client: WeaviateAsyncClient, config: Config,
                            vector: AnnotationVector | None) -> Enrichment:
    """The annotation enrichment (#328) the annotation collection's schema supports.

    Derived properties that the collection lacks are never written (Weaviate's
    auto-schema would add them with guessed types); the operator adds them with
    ``python -m semant_demo.maintenance.annotation_enrichment add-schema``.
    """
    try:
        missing, has_vector = await enrichment_schema(
            client, config.collectionNames, vector.target_vector if vector else None)
    except Exception as e:
        logger.warning("Could not read the annotation schema; annotation enrichment is off: %s", type(e).__name__)
        return Enrichment.disabled()
    if missing:
        logger.error("The annotation collection lacks the derived properties of #328 (%s): annotation text, "
                     "positions and vectors are not stored until python -m "
                     "semant_demo.maintenance.annotation_enrichment add-schema adds them.", ", ".join(missing))
        return Enrichment.disabled()
    if vector is not None and not has_vector:
        logger.error("The annotation collection has no named vector %s: contextual annotation vectors are not "
                     "stored until annotation_enrichment add-schema adds it.", vector.target_vector)
    return Enrichment(derived=True, vector=vector if has_vector else None)


async def detect_chunk_positions(client: WeaviateAsyncClient, config: Config) -> bool:
    """Whether the ``Chunks`` collection declares the chunk position properties of #463.

    Until it does, annotation text, context and positions are not derived (each span write
    reports ``derive_annotation``); the operator adds and fills them with
    ``python -m semant_demo.maintenance.chunk_positions``.
    """
    try:
        missing = await missing_position_properties(client, config.collectionNames)
    except Exception as e:
        logger.warning("Could not read the chunk schema; annotation positions are not derived: %s", type(e).__name__)
        return False
    if missing:
        logger.error("The chunk collection lacks the position properties of #463 (%s): annotation text, context "
                     "and positions are not derived until python -m semant_demo.maintenance.chunk_positions adds "
                     "and fills them (docs/DATA_MAINTENANCE.md).", ", ".join(missing))
    return not missing


async def detect_provenance(client: WeaviateAsyncClient, config: Config) -> bool:
    """Whether the annotation collection holds the provenance properties of #460.

    Until it does, annotations are written without provenance and without ``editVersion``
    checks; the operator adds them with
    ``python -m semant_demo.maintenance.annotation_provenance add-schema``.
    """
    try:
        missing = await provenance_schema(client, config.collectionNames)
    except Exception as e:
        logger.warning("Could not read the annotation schema; annotation provenance is off: %s", type(e).__name__)
        return False
    if missing:
        logger.error("The annotation collection lacks the provenance properties of #460 (%s): provenance and "
                     "edit conflicts are not recorded until python -m semant_demo.maintenance.annotation_provenance "
                     "add-schema adds them.", ", ".join(missing))
        return False
    return True


async def detect_attributes(client: WeaviateAsyncClient, config: Config) -> bool:
    """Whether the annotation collection holds the attribute properties of #331.

    Until it does, attribute definitions work but assignments are refused (503); the operator
    adds the properties with ``python -m semant_demo.maintenance.annotation_attributes add-schema``.
    """
    try:
        missing = await attribute_schema(client, config.collectionNames)
    except Exception as e:
        logger.warning("Could not read the annotation schema; attribute assignments are off: %s", type(e).__name__)
        return False
    if missing:
        logger.error("The annotation collection lacks the attribute properties of #331 (%s): attributes cannot be "
                     "assigned until python -m semant_demo.maintenance.annotation_attributes add-schema adds them.",
                     ", ".join(missing))
        return False
    return True


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
    tenant_activity: TenantActivity
    attributes: AttributeRepository
    annotation_vector: AnnotationVector | None = None
    """The configured contextual annotation vector; used only when the store holds it."""
    annotation_enrichment: Enrichment = field(default_factory=Enrichment.disabled)
    """What span writes derive, decided by the annotation collection's schema at connect."""
    rag: RagRegistry = field(default_factory=RagRegistry)
    weaviate: WeaviateRepositories | None = None
    _summarizer: TemplatedSearchResultsSummarizer | None = None
    _document_summarizer: TemplatedDocumentSummarizer | None = None

    @classmethod
    def create(cls, config: Config, llm_metrics: LlmMetrics | None = None,
               llm_transport: httpx.AsyncBaseTransport | None = None) -> "AppResources":
        """Construct resources without connecting to any external service.

        Raises ``LlmConfigurationError`` when the model tier catalog is invalid,
        ``ValidationError`` when the search or annotation vector configuration is, and ``ValueError``
        for invalid LLM quota or Topicer limit settings.
        """
        quota_policy = QuotaPolicy.from_config(config)
        llm = LlmGateway(ModelCatalog.load(config.LLM_MODELS_CONFIG), ProviderSettings.from_config(config),
                         llm_metrics, http_transport=llm_transport)
        engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        session_maker = async_sessionmaker(engine, autocommit=False, autoflush=True, expire_on_commit=False)
        return cls(config=config, engine=engine, session_maker=session_maker,
                   search_vectors=load_search_vectors(config),
                   annotation_vector=load_annotation_vector(config),
                   topicer=TopicerClient(config.TOPICER_URL, config.TOPICER_CONFIG_NAME, config.TOPICER_TIMEOUT,
                                         config.TOPICER_MAX_CHUNKS_PER_TAG),
                   llm=llm,
                   span_chat=FeatureChat(llm, "span_chat", temperature=config.SPAN_CHAT_TEMPERATURE,
                                         max_tokens=config.SPAN_CHAT_MAX_TOKENS),
                   corpus_overview=OverviewCache(config.CORPUS_OVERVIEW_MAX_AGE),
                   quota_ledger=QuotaLedger(session_maker), quota_policy=quota_policy,
                   tenant_activity=TenantActivity(session_maker, config.ANNOTATION_TENANT_TOUCH_SECONDS),
                   attributes=AttributeRepository(session_maker))

    async def connect_weaviate(self, connector: WeaviateConnector = connect_weaviate) -> None:
        """Open the application's Weaviate client; raises if it cannot be connected.

        Logs an error when the multi-tenant annotation collection does not exist (#327):
        span reads and writes then fail until the operator has run the migration. The
        application never creates or migrates it itself. Annotation enrichment (#328) and
        provenance (#460) and attributes (#331) are enabled as far as the collection's schema supports them
        (``detect_enrichment``, ``detect_provenance``, ``detect_attributes``); chunk text reads return the chunk
        positions of #463 when the chunk collection declares them (``detect_chunk_positions``).
        """
        client = await connector(self.config)
        try:
            self.weaviate = WeaviateRepositories.create(client, self.config)
        except Exception:
            await client.close()
            raise
        name = self.config.collectionNames.annotation_collection_name
        try:
            exists = await client.collections.exists(name)
        except Exception as e:
            logger.warning("Could not check the annotation collection %s: %s", name, type(e).__name__)
            return
        if not exists:
            logger.error("The annotation collection %s does not exist: annotations cannot be read or saved until "
                         "it is created and filled by python -m semant_demo.maintenance.annotation_migration "
                         "(docs/DATA_MAINTENANCE.md).", name)
            return
        self.annotation_enrichment = await detect_enrichment(client, self.config, self.annotation_vector)
        self.weaviate.spans.provenance = await detect_provenance(client, self.config)
        self.weaviate.spans.attributes = await detect_attributes(client, self.config)
        if self.annotation_enrichment.derived:
            self.weaviate.documents.positions = await detect_chunk_positions(client, self.config)

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
