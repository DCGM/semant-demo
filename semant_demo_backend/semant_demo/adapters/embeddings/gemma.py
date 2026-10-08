"""HTTP client of the embedding service (``EMBEDDING_SERVICE_HOST``/``_PORT``)."""
import httpx


class GemmaEmbeddings:
    """Query and document embeddings from the embedding service at ``base_url``.

    Built once per application by bootstrap from its config; holds no connection.
    HTTP errors propagate.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def embed_query(self, query: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/embed_query", json={"query": query}, timeout=36.0)
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/embed_documents", json={"texts": texts}, timeout=6.0)
            resp.raise_for_status()
            return resp.json()["embeddings"]

    async def embed_document(self, text: str) -> list[float]:
        """Embeds ``text`` as a document (HyDE: a query phrased as a document)."""
        return (await self.embed_documents([text]))[0]
