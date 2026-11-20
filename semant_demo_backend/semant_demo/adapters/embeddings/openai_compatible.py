"""HTTP client of an OpenAI-compatible ``/embeddings`` endpoint (e.g. vLLM)."""
import httpx


class OpenAICompatibleEmbeddings:
    """Query and document embeddings of ``model`` from ``base_url`` (including ``/v1``).

    ``query_prefix``/``document_prefix`` are prepended to the text, e.g. the instruction
    an asymmetric retrieval model expects; ``dimensions`` asks a Matryoshka model for a
    shorter vector. Built once per application by bootstrap; holds no connection. HTTP
    errors propagate.
    """

    def __init__(self, base_url: str, model: str, *, api_key: str = "", query_prefix: str = "",
                 document_prefix: str = "", dimensions: int | None = None, timeout: float = 36.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self.dimensions = dimensions
        self.timeout = timeout
        self.transport = transport

    async def embed_query(self, query: str) -> list[float]:
        return await self._embed(self.query_prefix + query)

    async def embed_document(self, text: str) -> list[float]:
        """Embeds ``text`` as a document (HyDE: a query phrased as a document)."""
        return await self._embed(self.document_prefix + text)

    async def _embed(self, text: str) -> list[float]:
        body: dict = {"model": self.model, "input": [text], "encoding_format": "float"}
        if self.dimensions is not None:
            body["dimensions"] = self.dimensions
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(transport=self.transport) as client:
            resp = await client.post(f"{self.base_url}/embeddings", json=body, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            [item] = resp.json()["data"]
            return item["embedding"]
