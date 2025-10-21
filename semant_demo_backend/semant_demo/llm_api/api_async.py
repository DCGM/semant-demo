import asyncio
import logging
from abc import abstractmethod
from asyncio import as_completed
from collections.abc import Iterable
from typing import AsyncGenerator

from ollama import AsyncClient
from openai import APIError, RateLimitError, AsyncOpenAI

from semant_demo.llm_api.base import APIOutput, APIModelResponseOllama, APIModelResponseOpenAI, APIBase, APIRequest


class APIAsync(APIBase):
    """
    Handles asynchronous requests to the API.
    """

    @abstractmethod
    async def process_single_request(self, request: APIRequest) -> APIOutput:
        """
        Processes a single request.

        :param request: Request dictionary.
        :return: Processed request
        """
        ...

    async def process_requests(self, requests: Iterable[APIRequest]) -> AsyncGenerator[APIOutput, None]:
        """
        Processes a list of requests.

        :param requests: Iterable of request dictionaries.
        :return: Processed requests
        """
        for o in as_completed(self.process_single_request(request) for request in requests):
            yield await o


class OpenAsyncAPI(APIAsync):
    """
    Handles asynchronous requests to the OpenAI API.
    """

    def __post_init__(self):
        self.client = AsyncOpenAI(
            api_key=self.api_key, base_url=self.base_url
        )
        self.semaphore = asyncio.Semaphore(self.concurrency)

    def convert_api_request_to_dict(self, request: APIRequest) -> dict:
        """
        Converts an APIRequest object to a dictionary suitable for OpenAI API call.

        :param request: APIRequest object.
        :return: Dictionary representation of the request.
        :raise ValueError: If unsopported arguments are provided.
        """
        if request.context_size is not None:
            raise ValueError("context_size is not supported by OpenAI API.")
        return {
            "custom_id": request.custom_id,
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_completion_tokens": request.max_completion_tokens,
            "response_format": request.response_format
        }

    async def process_single_request(self, request: APIRequest) -> APIOutput:
        async with self.semaphore:
            try:
                while True:
                    try:
                        response = await self.client.chat.completions.create(**self.convert_api_request_to_dict(request))
                        break
                    except RateLimitError:
                        logging.error(f"Rate limit reached. Waiting for {self.pool_interval} seconds.")
                        await asyncio.sleep(self.pool_interval)

                return APIOutput(
                    custom_id=request.custom_id,
                    response=APIModelResponseOpenAI(
                        body=response,
                        structured=request.response_format is not None
                    ),
                    error=None
                )
            except APIError as e:
                return APIOutput(
                    custom_id=request.custom_id,
                    response=None,
                    error=str(e)
                )


class OllamaAsyncAPI(APIAsync):
    """
    Handles asynchronous requests to the Ollama API.
    """

    def __post_init__(self):
        self.client = AsyncClient(host=self.base_url)
        self.semaphore = asyncio.Semaphore(self.concurrency)

    def convert_api_request_to_dict(self, request: APIRequest) -> dict:
        """
        Converts an APIRequest object to a dictionary suitable for Ollama API call.

        :param request: APIRequest object.
        :return: Dictionary representation of the request.
        """
        res = {
            "model": request.model,
            "messages": request.messages,
        }
        if request.response_format is not None:
            res["format"] = request.response_format if isinstance(request.response_format, dict) else request.response_format.model_json_schema()

        options = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.context_size is not None:
            options["num_ctx"] = request.context_size
        if request.max_completion_tokens is not None:
            options["num_predict"] = request.max_completion_tokens
        if options:
            res["options"] = options

        return res

    async def process_single_request(self, request: APIRequest) -> APIOutput:
        async with self.semaphore:
            try:
                response = await self.client.chat(**self.convert_api_request_to_dict(request))

                return APIOutput(
                    custom_id=request.custom_id,
                    response=APIModelResponseOllama(
                        body=response,
                        structured=request.response_format is not None
                    ),
                    error=None
                )
            except Exception as e:
                return APIOutput(
                    custom_id=request.custom_id,
                    response=None,
                    error=str(e)
                )
