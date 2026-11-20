"""Batched document embeddings for the benchmark store (#727): many texts per request to an
OpenAI-compatible ``/embeddings`` endpoint (e.g. vLLM). Query embeddings use the application's
own client (``adapters/embeddings/openai_compatible``), so a search embeds its query exactly as
the application does."""
from collections.abc import Sequence

import httpx


class BatchEmbeddings:
    def __init__(self, base_url: str, model: str, *, api_key: str = "", dimensions: int | None = None,
                 timeout: float = 60.0, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.dimensions, self.timeout, self.transport = dimensions, timeout, transport

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """One embedding per text, in their order, from one request. Raises ``ValueError`` when
        the answer does not hold one embedding per text, ``httpx.HTTPError`` on a failed request."""
        if not texts:
            return []
        body: dict = {"model": self.model, "input": list(texts), "encoding_format": "float"}
        if self.dimensions is not None:
            body["dimensions"] = self.dimensions
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(transport=self.transport) as client:
            response = await client.post(f"{self.base_url}/embeddings", json=body, headers=headers,
                                         timeout=self.timeout)
            response.raise_for_status()
            data = response.json()["data"]
        if len(data) != len(texts):
            raise ValueError(f"expected {len(texts)} embeddings, got {len(data)}")
        # OpenAI-compatible servers report each item's input position.
        return [item["embedding"] for item in sorted(data, key=lambda item: item.get("index", 0))]
