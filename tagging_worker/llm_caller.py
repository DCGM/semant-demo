"""LangChain Runnable wrapper for Ollama proxy."""
from ollama_proxy import OllamaProxy
from config import config
import asyncio
from langchain_core.prompt_values import PromptValue
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable


class OllamaProxyRunnable(Runnable):
    """LangChain-compatible Runnable wrapper for OllamaProxy."""
    
    def __init__(self):
        self.ollama_proxy = OllamaProxy(config.OLLAMA_URLS)
        self.ollama_model = config.OLLAMA_MODEL
        self.temperature = 0.0

    def set_model(self, model):
        """Set the Ollama model to use."""
        self.ollama_model = model

    def set_temperature(self, temperature):
        """Set the temperature for model responses."""
        self.temperature = temperature

    async def ainvoke(self, input, config=None):
        """Async invoke for LangChain chain integration."""
        # Handle PromptValue (e.g. from ChatPromptTemplate)
        if isinstance(input, PromptValue):
            input = input.to_string()

        # Handle list of messages
        elif isinstance(input, list) and all(isinstance(m, BaseMessage) for m in input):
            input = "\n".join([m.content for m in input])

        # Now input is guaranteed to be a string
        response = await self.ollama_proxy.call_ollama(self.ollama_model, input)
        return response

    def invoke(self, input, config=None):
        """Sync invoke - runs async code in event loop."""
        return asyncio.run(self.ainvoke(input, config))
