"""Base abstract provider for all LLM backends."""

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    # L-47: the abstract default was 4096 while deepseek.chat defaulted to 8192,
    # so a caller that relied on the declared default silently got a different
    # budget depending on which provider handled the request.
    DEFAULT_MAX_TOKENS = 8192

    # M-45: HTTP statuses that will NEVER succeed on retry.  Retrying them burns
    # 6 attempts x 2^5 s of backoff on a permanent auth/validation failure.
    NON_RETRYABLE_STATUS = frozenset({400, 401, 402, 403, 404, 405, 422})

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        ...

    @staticmethod
    def backoff_seconds(attempt: int) -> float:
        """Exponential backoff WITH jitter.

        M-45: `2**attempt` with no jitter makes every client that failed at the
        same moment retry at the same moment, so a rate-limited provider is hit by
        a synchronised thundering herd.
        """
        return (2**attempt) * (0.5 + random.random())

    def should_retry(self, exc: BaseException) -> bool:
        """M-45: a 400/401/403/404/422 is permanent; do not retry it."""
        import httpx

        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code not in self.NON_RETRYABLE_STATUS
        return True

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
