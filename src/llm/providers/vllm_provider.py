"""vLLM provider (stub)."""

from typing import Any

from .base import BaseProvider


class VLLMProvider(BaseProvider):
    def __init__(self, base_url: str = "http://127.0.0.1:8000/v1", model: str = "qwen3-14b", **kwargs) -> None:
        self._base_url = base_url
        self._model = model

    @property
    def provider_name(self) -> str:
        return "vllm"

    @property
    def default_model(self) -> str:
        return self._model

    async def chat(self, system_prompt: str, user_prompt: str, model: str | None = None, max_tokens: int = 4096, temperature: float = 0.1) -> dict[str, Any]:
        raise NotImplementedError("vLLM provider not yet implemented")

    async def close(self) -> None:
        pass
