import unittest
from unittest.mock import AsyncMock

import ollama
from ollama import ChatResponse
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from semant_demo.llm_api import OpenAsyncAPI, APIRequest, APIModelResponseOpenAI, OllamaAsyncAPI, APIModelResponseOllama


class TestOpenAsyncAPI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.api = OpenAsyncAPI(
            api_key="test_key",
            base_url="https://api.openai.com/v1",
            concurrency=5,
            pool_interval=1
        )
        self.client_mock = AsyncMock()
        self.api.client = self.client_mock

    def test_convert_api_request_to_dict(self):
        request = APIRequest(
            custom_id="test1",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello, world!"}],
            temperature=0.7,
            max_completion_tokens=100,
            response_format={"type": "json"}
        )

        res = self.api.convert_api_request_to_dict(request)

        self.assertDictEqual(
            {
                "custom_id": "test1",
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Hello, world!"}],
                "temperature": 0.7,
                "max_completion_tokens": 100,
                "response_format": {"type": "json"}
            },
            res
        )

    def test_convert_api_request_to_dict_invalid_arguments(self):
        request = APIRequest(
            custom_id="test1",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello, world!"}],
            temperature=0.7,
            context_size=2048,  # Unsupported argument
            max_completion_tokens=100,
            response_format={"type": "json"}
        )

        with self.assertRaises(ValueError) as context:
            self.api.convert_api_request_to_dict(request)

        self.assertEqual(str(context.exception), "context_size is not supported by OpenAI API.")

    async def test_process_single_request(self):
        request = APIRequest(
            custom_id="test1",
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello, world!"}],
            temperature=0.7,
            max_completion_tokens=100,
            response_format={"type": "json"}
        )

        self.client_mock.chat.completions.create.return_value = ChatCompletion(
            id="chatcmpl-123",
            choices=[
                Choice(
                    finish_reason="stop",
                    index=0,
                    logprobs=None,
                    message=ChatCompletionMessage(
                        content='{"response": "Hello! How can I assist you today?"}',
                        role="assistant"
                    )
                )
            ],
            object="chat.completion",
            created=1677652288,
            model="gpt-4"
        )

        result = await self.api.process_single_request(request)

        self.assertEqual(result.custom_id, "test1")
        self.assertIsNone(result.error)
        self.assertIsInstance(result.response, APIModelResponseOpenAI)
        self.assertEqual(result.response.get_raw_content(), '{"response": "Hello! How can I assist you today?"}')


class TestOllamaAsyncAPI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.api = OllamaAsyncAPI(
            api_key="test_key",
            base_url="https://api.ollama.com",
            concurrency=5,
            pool_interval=1
        )
        self.client_mock = AsyncMock()
        self.api.client = self.client_mock

    def test_convert_api_request_to_dict(self):
        request = APIRequest(
            custom_id="test1",
            model="llama2",
            messages=[{"role": "user", "content": "Hello, world!"}],
            temperature=0.7,
            max_completion_tokens=100,
            response_format={"type": "json"}
        )

        res = self.api.convert_api_request_to_dict(request)

        self.assertDictEqual(
            {
                "model": "llama2",
                "messages": [{"role": "user", "content": "Hello, world!"}],
                "options": {
                    "temperature": 0.7,
                    "num_predict": 100
                },
                "format": {"type": "json"}
            },
            res
        )

    async def test_process_single_request(self):
        request = APIRequest(
            custom_id="test1",
            model="llama2",
            messages=[{"role": "user", "content": "Hello, world!"}],
            temperature=0.7,
            max_completion_tokens=100,
            response_format={"type": "json"}
        )

        self.client_mock.chat.return_value = ChatResponse(
            message=ollama.Message(
                role="assistant",
                content='{"response": "Hello! How can I assist you today?"}'
            ),
            model="llama2"
        )

        result = await self.api.process_single_request(request)

        self.assertEqual(result.custom_id, "test1")
        self.assertIsNone(result.error)
        self.assertIsInstance(result.response, APIModelResponseOllama)
        self.assertEqual(result.response.get_raw_content(), '{"response": "Hello! How can I assist you today?"}')
