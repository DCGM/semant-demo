"""Pydantic models for tagging worker."""
from enum import Enum
from pydantic import BaseModel
from typing import Optional


class APIType(str, Enum):
    """Supported LLM API types."""
    ollama = "OLLAMA"
    openai = "OPENAI"
    google = "GOOGLE"


class TaggingConfigParams(BaseModel):
    """Parameters for tagging LLM model."""
    model_type: APIType
    model_name: str
    temperature: float = 1.0


class TaggingConfig(BaseModel):
    """Configuration for a tagging task."""
    name: str
    description: str
    class_name: str
    prompt_template: Optional[str] = None
    params: TaggingConfigParams


class TaggingTaskReqTemplate(BaseModel):
    """Request to start a tagging task."""
    tag_name: str
    tag_shorthand: str
    tag_color: str
    tag_pictogram: str
    tag_definition: str
    tag_examples: list[str]
    collection_name: str
    task_config: TaggingConfig
