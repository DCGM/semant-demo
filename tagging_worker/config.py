"""Configuration for tagging worker."""
import os


class Config:
    """Worker configuration - minimal set needed for tagging operations."""
    
    def __init__(self):
        # Redis connection
        self.REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        self.REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
        
        # Weaviate connection
        self.WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
        self.WEAVIATE_PORT = int(os.getenv("WEAVIATE_PORT", 50051))
        
        # LLM API keys
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
        self.GOOGLE_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-pro")
        
        # Ollama configuration
        self.OLLAMA_URLS = os.getenv("OLLAMA_URLS", "http://localhost:11434").split(",")
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
        
        # Default tagging prompt template
        self.DEFAULT_TAG_TEMPLATE = """Tag name: {tag_name}
Definition: {tag_definition}
Examples: {tag_examples}

Does this content match the tag?
Content: {content}

Respond only with True or False."""


config = Config()
