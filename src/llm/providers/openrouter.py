"""OpenRouter provider (stub)."""

from typing import Any

from .base import BaseProvider


class OpenRouterProvider(BaseProvider):
    def __init__(self, base_url: str = "https://openrouter.ai/api/v1", api_key: str = "", model: str = "qwen3-14b", **kwargs) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def default_model(self) -> str:
        return self._model

    async def chat(self, system_prompt: str, user_prompt: str, model: str | None = None, max_tokens: int = 4096, temperature: float = 0.1) -> dict[str, Any]:
        raise NotImplementedError("OpenRouter provider not yet implemented")

    async def close(self) -> None:
        pass
