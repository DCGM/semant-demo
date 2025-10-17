# LLM API Wrapper
This module provides a simple wrapper around various Large Language Model (LLM) APIs, allowing for easy integration and interaction with different LLM providers.

This wrapper is using `classconfig` package which allows for easy creation of instances from configuration files or dictionaries. It can be further integrated as part of another configurable class, see [Full Example Usage with Configurable Class](#full-example-usage-with-configurable-class) section below for more details.

## Supported LLM Providers
- OpenAI (`OpenAsyncAPI`) - Async API for OpenAI compatible APIs
- Ollama (`OllamaAsyncAPI`) - Async API for Ollama

## Standalone Usage
You can use the LLM API wrapper directly by creating an instance of the desired LLM class and calling its methods.

```python
from semant_demo.llm_api import OllamaAsyncAPI, APIRequest, APIOutput
api = OllamaAsyncAPI(
    api_key="your_api_key",
    base_url="http://localhost:11434",
)
request = APIRequest(
    custom_id="test",
    model="gpt-oss:20b",
    messages=[
        {"role": "user", "content": "Hello, how are you?"}
    ],
)
output: APIOutput = await api.process_single_request(request)
output.response.get_raw_content().strip()   # Get the raw response content regardless of the provider
```

## Full Example Usage with Configurable Class
Let's assume you want to provide new tool to SemANT backend that uses LLM API, for the sake of this example we will create a simple translator.

```python
from semant_demo.llm_api import APIAsync, APIRequest, APIOutput, OllamaAsyncAPI
from semant_demo.utils.template import Template, TemplateTransformer
from classconfig import ConfigurableSubclassFactory, ConfigurableMixin, ConfigurableValue
from classconfig.configurable import CreatableMixin

class Translator(ConfigurableMixin, CreatableMixin):
    api: APIAsync = ConfigurableSubclassFactory(APIAsync, "API configuration.", user_default=OllamaAsyncAPI)
    model: str = ConfigurableValue(user_default="gpt-oss:20b", desc="Model to use for translation.")
    system_prompt: Template = ConfigurableValue(
        user_default="Your task is to translate given text into the target language specified by the user.",
        desc="System prompt for translation.",
        transform=TemplateTransformer()
    )
    user_prompt: Template = ConfigurableValue(
        user_default="Translate the following text to {{target_language}}:\n\n{{text}}",
        desc="User prompt for translation.",
        transform=TemplateTransformer()
    )

    async def __call__(self, text: str, target_language: str) -> str:
        messages = [
            {"role": "system", "content": self.system_prompt.render({})},
            {"role": "user", "content": self.user_prompt.render({"text": text, "target_language": target_language})},
        ]
        request = APIRequest(
            custom_id="translation_request",
            model=self.model,
            messages=messages,
        )
        output: APIOutput = await self.api.process_single_request(request)
        return output.response.get_raw_content().strip()
```

In the example above, we created a `Translator` class that uses the LLM API to translate text into a specified target language. The class is configurable, allowing you to specify the API provider, model, and prompts via configuration files or dictionaries.

Now we need yaml configuration to create an instance of the `Translator` class using Ollama API. We can simply create a default one like this:

```python
from classconfig import Config
Config(Translator).save("translator_config.yaml")
```

This will create a `translator_config.yaml` file with the default configuration and you can modify it as needed:

```yaml
api:  # API configuration.
  cls: OllamaAsyncAPI  # name of class that is subclass of APIAsync
  config: # configuration for defined class
    api_key: your_key # API key.
    base_url: your_URL # Base URL for API.
    pool_interval: 300 # Interval in seconds for checking status.
    process_requests_interval: 1 # Interval in seconds between sending requests when processed synchronously.
    concurrency: 10 # Maximum number of concurrent requests to the API. This is used with async processing.
model: gpt-oss:20b # Model to use for translation.
system_prompt: Your task is to translate given text into the target language specified
  by the user. # System prompt for translation.
user_prompt: "Translate the following text to {{target_language}}:\n\n{{text}}" # User prompt for translation.
```
We used the `CreatableMixin` which allows us to use `create` method to create an instance from the configuration file directly:

```python
translator = Translator.create("translator_config.yaml")
translated_text = await translator("Hello, how are you?", "Spanish")
print(translated_text)
```                                         