"""Google Gemini provider (stub)."""

from typing import Any

from .base import BaseProvider


class GeminiProvider(BaseProvider):
    def __init__(self, base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai", api_key: str = "", model: str = "gemini-2.5-flash", **kwargs) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return self._model

    async def chat(self, system_prompt: str, user_prompt: str, model: str | None = None, max_tokens: int = 4096, temperature: float = 0.1) -> dict[str, Any]:
        raise NotImplementedError("Gemini provider not yet implemented")

    async def close(self) -> None:
        pass
