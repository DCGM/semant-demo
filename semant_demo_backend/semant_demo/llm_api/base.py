from abc import ABC, abstractmethod
from typing import Optional, Literal, Union

from classconfig import ConfigurableValue, ConfigurableMixin
from classconfig.validators import StringValidator, MinValueIntegerValidator
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, Field
from ollama import ChatResponse


class APIConfigMixin(ConfigurableMixin):
    """
    To have a consistent API configuration (one configuration file from user perspective),
    we use this mixin to define the API configuration.
    """

    api_key: str = ConfigurableValue(desc="API key.", validator=StringValidator())
    base_url: Optional[str] = ConfigurableValue(desc="Base URL for API.", user_default=None, voluntary=True)
    pool_interval: Optional[int] = ConfigurableValue(
        desc="Interval in seconds for checking status.",
        user_default=300,
        voluntary=True,
        validator=lambda x: x is None or x > 0)
    process_requests_interval: Optional[int] = ConfigurableValue(
        desc="Interval in seconds between sending requests when processed synchronously.",
        user_default=1,
        voluntary=True,
        validator=lambda x: x is None or x >= 0)
    concurrency: int = ConfigurableValue(
        desc="Maximum number of concurrent requests to the API. This is used with async processing.",
        user_default=10, voluntary=True, validator=MinValueIntegerValidator(1)
    )


class APIRequest(BaseModel):
    """
    Represents a request to an API.
    """
    custom_id: str  # Custom ID for the request
    model: str  # Model to use for the request
    messages: list[dict]  # List of messages in the request
    temperature: Optional[float] = None  # Temperature for the model
    context_size: Optional[int] = None  # Context size for the model
    max_completion_tokens: Optional[int] = None  # Maximum number of tokens to generate
    response_format: Optional[dict | BaseModel] = None  # Format of the response, if any


class APIModelResponse(BaseModel, ABC):
    """
    Represents the response from an API Model.
    """
    structured: bool

    @abstractmethod
    def get_raw_content(self, choice: Optional[int] = None) -> str:
        """
        Returns the raw content of the response.

        :param choice: Optional index of the choice to return content from.
        """
        ...


class APIModelResponseOpenAI(APIModelResponse):
    type: Literal["openai"] = "openai"
    body: ChatCompletion

    def get_raw_content(self, choice: Optional[int] = None) -> str:
        """
        Returns the raw content of the response.

        :param choice: Optional index of the choice to return content from.
        :return: Raw content of the response.
        """
        if choice is None:
            choice = 0

        return self.body.choices[choice].message.content


class APIModelResponseOllama(APIModelResponse):
    type: Literal["ollama"] = "ollama"
    body: ChatResponse

    def get_raw_content(self, choice: Optional[int] = None) -> str:
        if choice is not None:
            raise ValueError("Ollama API does not support multiple choices.")

        return self.body.message.content


class APIOutput(BaseModel):
    """
    Represents the output of an API call.
    """
    custom_id: str
    response: Optional[Union[APIModelResponseOpenAI, APIModelResponseOllama]] = Field(None, discriminator='type')
    error: Optional[str] = None


class APIBase(ABC, APIConfigMixin):
    """
    Base class for API implementations.
    """
    ...
