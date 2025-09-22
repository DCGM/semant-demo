import asyncio
from typing import List, Optional
from ollama import AsyncClient
import random

class OllamaProxy:
    def __init__(self, ollama_urls: List[str]):
        self.ollama_urls = ollama_urls
        self.clients = [AsyncClient(host=url) for url in ollama_urls]
        self._counter = 0
        self._lock = asyncio.Lock()

    async def call_ollama(self, model: str, prompt: str) -> Optional[str]:
        async with self._lock:
            idx = self._counter % len(self.clients)
            self._counter += 1
        client = self.clients[idx]
        try:
            response = await client.generate(model=model, prompt=prompt)
        except Exception as e:
            print(f"Error calling model {model} at {self.ollama_urls[idx]}: {e}")
            return None

        if isinstance(response, dict) and "choices" in response and response["choices"]:
            choice = response["choices"][0]
            if isinstance(choice, dict) and "message" in choice:
                return choice["message"].get("content", "")
            if isinstance(choice, dict) and "text" in choice:
                return choice.get("text", "")
        for key in ("response", "result"):
            if key in response:
                return response.get(key, "")
        return None
    
    async def call_ollama_chat(self, model: str, messages: list[dict]) -> str:
        client = random.choice(self.clients)
        try:
            response = await client.chat(model=model, messages=messages, stream=False)
            return response['message']['content']
        except Exception as e:
            print(f"Error calling model: {model} at {client.host}: {e}")
            return "Sorry, error occurred while genereting response."