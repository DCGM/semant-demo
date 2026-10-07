"""Construction and release of application-scoped resources.

One ``AppResources`` instance belongs to one running application (one lifespan).
It is created at startup, stored on ``app.state.resources``, and closed at shutdown,
so the same application can be started and stopped repeatedly in one process.
"""
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from weaviate import WeaviateAsyncClient

from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.config import Config
from semant_demo.rag.rag_factory import RagRegistry
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

logger = logging.getLogger(__name__)

WeaviateConnector = Callable[[Config], Awaitable[WeaviateAsyncClient]]


@dataclass
class WeaviateRepositories:
    """Repositories sharing the application's one Weaviate client."""
    client: WeaviateAsyncClient
    documents: DocumentRepository
    tags: TagRepository
    collections: UserCollectionRepository
    legacy: WeaviateAbstraction
    """Transitional facade for callers not migrated yet (see its module docstring)."""

    @classmethod
    def create(cls, client: WeaviateAsyncClient, config: Config) -> "WeaviateRepositories":
        names = config.collectionNames
        return cls(
            client=client,
            documents=DocumentRepository(client, names),
            tags=TagRepository(client, names),
            collections=UserCollectionRepository(client, names),
            legacy=WeaviateAbstraction(client, names),
        )


@dataclass
class AppResources:
    config: Config
    engine: AsyncEngine
    session_maker: async_sessionmaker
    rag: RagRegistry = field(default_factory=RagRegistry)
    weaviate: WeaviateRepositories | None = None
    _summarizer: TemplatedSearchResultsSummarizer | None = None

    @classmethod
    def create(cls, config: Config) -> "AppResources":
        """Construct resources without connecting to any external service."""
        engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        session_maker = async_sessionmaker(engine, autocommit=False, autoflush=True, expire_on_commit=False)
        return cls(config=config, engine=engine, session_maker=session_maker)

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
            self._summarizer = TemplatedSearchResultsSummarizer.create(self.config.SEARCH_SUMMARIZER_CONFIG)
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
