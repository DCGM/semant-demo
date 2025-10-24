from semant_demo.ollama_proxy import OllamaProxy
from semant_demo.config import config
import asyncio
from langchain_core.prompt_values import PromptValue
from langchain_core.messages import BaseMessage
from langchain.schema.runnable import Runnable

class OllamaProxyRunnable(Runnable):
    def __init__(self):
        self.ollama_proxy = OllamaProxy(config.OLLAMA_URLS)
        self.ollama_model = config.OLLAMA_MODEL

    async def ainvoke(self, input, config=None):
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
        return asyncio.run(self.ainvoke(input, config))