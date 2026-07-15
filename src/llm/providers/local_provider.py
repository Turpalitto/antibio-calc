"""Local OpenAI-compatible provider (stub — placeholder for future Qwen3-14B)."""

from typing import Any

from .base import BaseProvider


class LocalProvider(BaseProvider):
    def __init__(self, base_url: str = "http://127.0.0.1:11434/v1", model: str = "qwen3:14b", **kwargs) -> None:
        self._base_url = base_url
        self._model = model

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def default_model(self) -> str:
        return self._model

    async def chat(self, system_prompt: str, user_prompt: str, model: str | None = None, max_tokens: int = 4096, temperature: float = 0.1) -> dict[str, Any]:
        raise NotImplementedError("Local provider not yet implemented — deploy Qwen3-14B on Ollama/vLLM first")

    async def close(self) -> None:
        pass
