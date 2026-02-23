"""
Calling metacentrum API

Available models:
gpt-oss-120b
qwen3-reranker-4b
llama-4-scout-17b-16e-instruct
qwen3-embedding-4b
mxbai-embed-large:latest
multilingual-e5-large-instruct
nomic-embed-text-v2-moe
nomic-embed-text-v1.5
mistral-large
qwen3-coder
kimi-k2.5
deepseek-v3.2
deepseek-v3.2-thinking
qwen3-coder-next
qwen3.5
qwen3-coder-30b
glm-4.7
"""
from pydantic_ai import Agent
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import os
model = OpenAIChatModel(
    'gpt-oss-120b',
    provider=OpenAIProvider(
        base_url="https://llm.ai.e-infra.cz/v1",
        api_key=os.getenv("E_INFRA_KEY"),
    ),
)

agent = Agent(model)

result = agent.run_sync("What model is you?")
print(result.output)