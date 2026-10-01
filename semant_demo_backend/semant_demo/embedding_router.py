from openai import AsyncOpenAI
from ollama import AsyncClient

from semant_demo.config import config
from semant_demo.schemas import EmbeddingProvider


def _resolve_embedding_config(vector_name: str | None) -> tuple[str, dict[str, str]]:
    resolved_vector = config.resolve_chunk_vector(vector_name)
    embedding_config = config.get_chunk_vector_embedding_config(resolved_vector)
    return resolved_vector, embedding_config


async def _get_ollama_embeddings(texts: list[str], model: str, base_url: str) -> list[list[float]]:
    client = AsyncClient(host=base_url)
    try:
        response = await client.embed(model=model, input=texts)
        embeddings = response.get("embeddings") if isinstance(response, dict) else response.embeddings
    except AttributeError:
        embeddings = []
        for text in texts:
            response = await client.embeddings(model=model, prompt=text)
            embedding = response.get("embedding") if isinstance(response, dict) else response.embedding
            embeddings.append(embedding)

    if not embeddings:
        raise RuntimeError(f"Ollama returned no embeddings for model '{model}'")
    return embeddings


async def _get_openrouter_embeddings(
    texts: list[str],
    model: str,
    base_url: str,
    api_key: str | None,
) -> list[list[float]]:
    if not api_key:
        raise RuntimeError("OpenRouter embedding API key is not configured")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


async def get_documents_embeddings(
    texts: list[str],
    vector_name: str | None = None,
) -> list[list[float]]:
    resolved_vector, embedding_config = _resolve_embedding_config(vector_name)
    provider = embedding_config.get("provider")
    model = embedding_config.get("model")
    base_url = embedding_config.get("base_url")

    if not model or not base_url:
        raise RuntimeError(f"Embedding config for vector '{resolved_vector}' must define model and base_url")

    if provider == EmbeddingProvider.ollama.value:
        return await _get_ollama_embeddings(texts, model=model, base_url=base_url)
    if provider == EmbeddingProvider.openrouter.value:
        return await _get_openrouter_embeddings(
            texts,
            model=model,
            base_url=base_url,
            api_key=embedding_config.get("api_key"),
        )

    raise RuntimeError(f"Unsupported embedding provider '{provider}' for vector '{resolved_vector}'")


async def get_query_embedding(query: str, vector_name: str | None = None) -> list[float]:
    embeddings = await get_documents_embeddings([query], vector_name=vector_name)
    return embeddings[0]


async def get_hyde_document_embedding(text: str, vector_name: str | None = None) -> list[float]:
    embeddings = await get_documents_embeddings([text], vector_name=vector_name)
    return embeddings[0]
