import os
from typing import Any, Dict
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

try:
    from langchain_ollama import OllamaEmbeddings, ChatOllama
    OLLAMA_AVAILABLE = True
except ImportError:
    try:
        from langchain_community.embeddings import OllamaEmbeddings
        from langchain_community.llms import Ollama as ChatOllama
        OLLAMA_AVAILABLE = True
    except ImportError:
        OLLAMA_AVAILABLE = False
        OllamaEmbeddings = None
        ChatOllama = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    ChatGoogleGenerativeAI = None


def get_model(model_id: str, **kwargs) -> Any:
    if model_id == "OPENAI_EMBEDDING_MODEL":
        return create_openai_embedding_model(**kwargs)
    elif model_id == "OPENAI_GENERATION_MODEL":
        return create_openai_generation_model(**kwargs)
    elif model_id == "OLLAMA_EMBEDDING_MODEL":
        return create_ollama_embedding_model(**kwargs)
    elif model_id == "OLLAMA_GENERATION_MODEL":
        return create_ollama_generation_model(**kwargs)
    elif model_id == "GEMINI_GENERATION_MODEL":
        return create_gemini_generation_model(**kwargs)
    elif model_id == "GENERATION_MODEL":
        # Handle the case where model_id is just "GENERATION_MODEL"
        # Check if it's a Gemini model based on the model_name
        model_name = kwargs.get("model_name", "")
        if "gemini" in model_name.lower():
            return create_gemini_generation_model(**kwargs)
        else:
            return create_ollama_generation_model(**kwargs)
    else:
        raise ValueError(f"Unknown model: {model_id}")


# Create a simple alias for backward compatibility
class ModelProvider:
    def get(self, model_id: str, **kwargs):
        return get_model(model_id, **kwargs)

models = ModelProvider()


def create_openai_embedding_model(**kwargs) -> OpenAIEmbeddings:
    api_key = os.getenv(kwargs.get("api_key_env", "OPENAI_API_KEY"))
    if not api_key:
        raise ValueError(f"Environment variable {kwargs.get('api_key_env', 'OPENAI_API_KEY')} not set")
    
    return OpenAIEmbeddings(
        model=kwargs.get("model_name", "text-embedding-3-small"),
        openai_api_key=api_key
    )


def create_openai_generation_model(**kwargs) -> ChatOpenAI:
    api_key = os.getenv(kwargs.get("api_key_env", "OPENAI_API_KEY"))
    if not api_key:
        raise ValueError(f"Environment variable {kwargs.get('api_key_env', 'OPENAI_API_KEY')} not set")
    
    return ChatOpenAI(
        model=kwargs.get("model_name", "gpt-4o-mini"),
        openai_api_key=api_key,
        temperature=kwargs.get("temperature", 0.1),
        max_tokens=kwargs.get("max_tokens", 2000)
    )


def create_ollama_embedding_model(**kwargs) -> OllamaEmbeddings:
    if not OLLAMA_AVAILABLE:
        raise ImportError("Ollama models are not available. Please install langchain-ollama or langchain-community")
    
    return OllamaEmbeddings(
        model=kwargs.get("model_name", "nomic-embed-text:latest"),
        base_url=kwargs.get("base_url", "http://localhost:11434")
    )


def create_ollama_generation_model(**kwargs) -> ChatOllama:
    if not OLLAMA_AVAILABLE:
        raise ImportError("Ollama models are not available. Please install langchain-ollama or langchain-community")
    
    return ChatOllama(
        model=kwargs.get("model_name", "gemma3:1b"),
        base_url=kwargs.get("base_url", "http://localhost:11434"),
        temperature=kwargs.get("temperature", 0.1),
        num_predict=kwargs.get("max_tokens", 2000)
    )


def create_gemini_generation_model(**kwargs) -> ChatGoogleGenerativeAI:
    if not GEMINI_AVAILABLE:
        raise ImportError("Gemini models are not available. Please install langchain-google-genai")
    
    api_key = os.getenv(kwargs.get("api_key_env", "GEMINI_API_KEY"))
    if not api_key:
        raise ValueError(f"Environment variable {kwargs.get('api_key_env', 'GEMINI_API_KEY')} not set")
    
    return ChatGoogleGenerativeAI(
        model=kwargs.get("model_name", "gemini-2.5-flash"),
        temperature=kwargs.get("temperature", 0),
        max_tokens=kwargs.get("max_tokens", None),
        timeout=kwargs.get("timeout", None),
        max_retries=kwargs.get("max_retries", 2),
        google_api_key=api_key
    )


def load_model_config(config_path: str = "config/models.yaml") -> Dict[str, Any]:
    import yaml
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        raise ValueError(f"Could not load model config from {config_path}: {e}")


def get_configured_model(model_type: str = "generation", config_path: str = "config/models.yaml"):
    config = load_model_config(config_path)
    
    if model_type == "generation":
        model_config = config.get("generation-model", {})
    elif model_type == "embedding":
        model_config = config.get("embedding-model", {})
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    
    model_id = model_config.get("model_id")
    if not model_id:
        raise ValueError(f"No model_id found for {model_type}-model in config")
    
    # Remove model_id from kwargs to pass to get_model
    model_kwargs = {k: v for k, v in model_config.items() if k != "model_id"}
    
    return get_model(model_id, **model_kwargs)

