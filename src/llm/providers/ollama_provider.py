"""Ollama provider (stub)."""

from typing import Any

from .base import BaseProvider


class OllamaProvider(BaseProvider):
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen3:14b", **kwargs) -> None:
        self._base_url = base_url
        self._model = model

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def default_model(self) -> str:
        return self._model

    async def chat(self, system_prompt: str, user_prompt: str, model: str | None = None, max_tokens: int = 4096, temperature: float = 0.1) -> dict[str, Any]:
        raise NotImplementedError("Ollama provider not yet implemented")

    async def close(self) -> None:
        pass
