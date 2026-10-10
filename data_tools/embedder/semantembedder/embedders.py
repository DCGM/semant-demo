import abc
import os
from typing import Optional

from classconfig import ConfigurableMixin, CreatableMixin, ConfigurableValue
from jinja2 import Environment


class Embedder(ConfigurableMixin, CreatableMixin, abc.ABC):
    """Base class for configurable asynchronous embedders."""

    @abc.abstractmethod
    def render(self, database_record: dict) -> str:
        """Create the text that should be embedded from the database record.

        Args:
            database_record: Dictionary of database record fields.

        Returns:
            Text to embed. Empty (whitespace only) text means the record is skipped.
        """
        pass

    @abc.abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Texts to embed.

        Returns:
            One embedding per text, in the same order.
        """
        pass

    async def close(self) -> None:
        """Release resources (e.g. HTTP connections)."""
        pass


class VLLMEmbedder(Embedder):
    """Embedder calling the OpenAI-compatible /v1/embeddings endpoint (e.g. vLLM started with `--task embed`)."""

    base_url: str = ConfigurableValue(
        desc="Base URL of the OpenAI-compatible API (vLLM server)",
        user_default="http://localhost:8000/v1"
    )
    api_key: Optional[str] = ConfigurableValue(
        desc="API Key (optional, defaults to OPENAI_API_KEY environment variable)",
        user_default=None,
        voluntary=True
    )
    model_name: str = ConfigurableValue(
        desc="Name of the served embedding model (as reported by /v1/models)",
        user_default="my-embedder"
    )
    input_template: str = ConfigurableValue(
        desc="Jinja2 template for the embedded text. You can use any record fields. Use it also for instruction prefixes (e.g. 'passage: {{ text }}').",
        user_default="{{ text }}"
    )
    dimensions: Optional[int] = ConfigurableValue(
        desc="Requested output dimension (only for models supporting Matryoshka embeddings)",
        user_default=None,
        voluntary=True
    )
    truncate_prompt_tokens: Optional[int] = ConfigurableValue(
        desc="vLLM specific: truncate inputs to this number of tokens instead of failing on too long inputs (-1 = model max length)",
        user_default=None,
        voluntary=True
    )
    extra_body: Optional[dict] = ConfigurableValue(
        desc="Additional parameters sent in the request body (vLLM specific options)",
        user_default=None,
        voluntary=True
    )
    timeout: float = ConfigurableValue(
        desc="Timeout of a single request in seconds",
        user_default=120.0
    )
    max_retries: int = ConfigurableValue(
        desc="Maximum number of retries of a failed request (with exponential backoff)",
        user_default=5
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None
        self.jinja_env = Environment()
        self.input_template_compiled = self.jinja_env.from_string(self.input_template)

    def _init_client(self):
        if self._client is not None:
            return

        from openai import AsyncOpenAI
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY") or "dummy-key"
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries
        )

    def render(self, database_record: dict) -> str:
        return self.input_template_compiled.render(**database_record)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._init_client()

        extra_body = dict(self.extra_body or {})
        if self.truncate_prompt_tokens is not None:
            extra_body["truncate_prompt_tokens"] = self.truncate_prompt_tokens

        kwargs = {}
        if self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions

        response = await self._client.embeddings.create(
            model=self.model_name,
            input=texts,
            encoding_format="float",
            extra_body=extra_body or None,
            **kwargs
        )

        # the order of response.data is not guaranteed, it is identified by index
        embeddings = [None] * len(texts)
        for item in response.data:
            embeddings[item.index] = item.embedding

        if any(e is None for e in embeddings):
            raise RuntimeError(f"Embedding API returned {len(response.data)} embeddings for {len(texts)} inputs.")

        return embeddings

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
