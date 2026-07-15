from .anthropic import AnthropicProvider
from .deepseek import DeepSeekProvider
from .openrouter import OpenRouterProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from .vllm_provider import VLLMProvider
from .local_provider import LocalProvider

PROVIDER_MAP = {
    "anthropic": AnthropicProvider,
    "deepseek": DeepSeekProvider,
    "openrouter": OpenRouterProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "vllm": VLLMProvider,
    "local": LocalProvider,
}

__all__ = [
    "PROVIDER_MAP",
    "AnthropicProvider",
    "DeepSeekProvider",
    "OpenRouterProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "OllamaProvider",
    "VLLMProvider",
    "LocalProvider",
]
