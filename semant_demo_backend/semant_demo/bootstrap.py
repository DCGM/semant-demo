"""Construction and release of application-scoped resources.

One ``AppResources`` instance belongs to one running application (one lifespan).
It is created at startup, stored on ``app.state.resources``, and closed at shutdown,
so the same application can be started and stopped repeatedly in one process.
"""
import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from semant_demo.config import Config
from semant_demo.rag.rag_factory import RagRegistry
from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

logger = logging.getLogger(__name__)


@dataclass
class AppResources:
    config: Config
    engine: AsyncEngine
    session_maker: async_sessionmaker
    rag: RagRegistry = field(default_factory=RagRegistry)
    _searcher: WeaviateAbstraction | None = None
    _searcher_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _summarizer: TemplatedSearchResultsSummarizer | None = None

    @classmethod
    def create(cls, config: Config) -> "AppResources":
        """Construct resources without connecting to any external service."""
        engine = create_async_engine(config.SQL_DB_URL, pool_size=20, max_overflow=60)
        session_maker = async_sessionmaker(engine, autocommit=False, autoflush=True, expire_on_commit=False)
        return cls(config=config, engine=engine, session_maker=session_maker)

    async def get_searcher(self) -> WeaviateAbstraction:
        # Weaviate is connected on first use, as before; startup does not require it.
        if self._searcher is None:
            async with self._searcher_lock:
                if self._searcher is None:
                    self._searcher = await WeaviateAbstraction.create(self.config)
        return self._searcher

    def get_summarizer(self) -> TemplatedSearchResultsSummarizer:
        if self._summarizer is None:
            self._summarizer = TemplatedSearchResultsSummarizer.create(self.config.SEARCH_SUMMARIZER_CONFIG)
        return self._summarizer

    async def close(self) -> None:
        """Release everything this instance opened; safe after partial startup."""
        searcher, self._searcher = self._searcher, None
        self._summarizer = None
        self.rag = RagRegistry()
        try:
            if searcher is not None:
                await searcher.close()
        except Exception:
            logger.exception("Failed to close Weaviate client.")
        finally:
            await self.engine.dispose()
