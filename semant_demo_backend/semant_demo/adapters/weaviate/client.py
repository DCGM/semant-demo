"""Opening the Weaviate client. The application does this once, at startup (bootstrap)."""
import weaviate
from weaviate import WeaviateAsyncClient

from semant_demo.config import Config


class WeaviateUnavailable(RuntimeError):
    """Weaviate could not be connected or did not report ready."""


async def connect_weaviate(config: Config) -> WeaviateAsyncClient:
    """A connected client for the configured Weaviate, verified ready.

    ``skip_init_checks`` skips the client's PyPI version lookup (a request to pypi.org on
    every connection) and its gRPC ping; readiness is checked explicitly instead.
    """
    client = weaviate.use_async_with_custom(
        http_host=config.WEAVIATE_HOST, http_port=config.WEAVIATE_REST_PORT, http_secure=False,
        grpc_host=config.WEAVIATE_HOST, grpc_port=config.WEAVIATE_GRPC_PORT, grpc_secure=False,
        skip_init_checks=True,
    )
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    try:
        await client.connect()
        ready = await client.is_ready()
    except Exception as e:
        await client.close()
        raise WeaviateUnavailable(f"Cannot connect to Weaviate at {endpoint}: {e}") from e
    if not ready:
        await client.close()
        raise WeaviateUnavailable(f"Weaviate at {endpoint} is not ready.")
    return client
