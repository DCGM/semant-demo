import httpx
from config import config

EMBEDDING_URL = "http://localhost:8001"

async def get_query_embedding(query: str) -> list[float]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{config.GEMMA_URL}/embed_query",
            json={"query": query},
            timeout=6.0
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

async def get_documents_embeddings(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{config.GEMMA_URL}/embed_documents",
            json={"texts": texts},
            timeout=6.0
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]