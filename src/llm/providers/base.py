"""Base abstract provider for all LLM backends."""

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        ...

    async def healthcheck(self) -> bool:
        try:
            resp = await self.chat(
                "You are a test assistant.",
                "Respond with exactly: OK",
                max_tokens=10,
                temperature=0.0,
            )
            content = resp["choices"][0]["message"]["content"].strip()
            return content == "OK"
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        return [self.default_model]

    @abstractmethod
    async def close(self) -> None: ...
