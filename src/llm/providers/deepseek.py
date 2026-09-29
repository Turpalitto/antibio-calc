"""DeepSeek provider via OpenCode Go proxy."""

import asyncio
import logging
from typing import Any

import httpx

from .base import BaseProvider

logger = logging.getLogger(__name__)


class DeepSeekProvider(BaseProvider):
    def __init__(
        self,
        base_url: str = "https://opencode.ai/zen/go/v1",
        api_key: str = "",
        model: str = "deepseek-v4-flash",
        timeout: int = 300,
        max_retries: int = 6,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def default_model(self) -> str:
        return self._model

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # L-47: matches the declared base-class default.
            "max_tokens": max_tokens if max_tokens is not None else self.DEFAULT_MAX_TOKENS,
            "temperature": temperature,
        }
        # L-47: `**kwargs` was accepted and silently discarded, so a caller's
        # `response_format=...` had no effect and looked like it did.
        payload.update({k: v for k, v in kwargs.items() if k not in ("provider", "client")})

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._http.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001 - classified below
                # M-45: `except (HTTPStatusError, RequestError, Exception)` was
                # decorative -- `Exception` subsumes both -- so a permanent 401
                # was retried 6 times with 2^5 s of backoff.
                last_exc = exc
                if not self.should_retry(exc):
                    logger.error(
                        "DeepSeek request failed permanently (status %s): %s",
                        getattr(getattr(exc, "response", None), "status_code", "n/a"), exc,
                    )
                    raise
                if attempt >= self._max_retries - 1:
                    raise
                wait = self.backoff_seconds(attempt)
                logger.warning(
                    "DeepSeek attempt %d/%d failed: %s: %s, retry in %.1fs",
                    attempt + 1, self._max_retries, type(exc).__name__, exc, wait,
                )
                await asyncio.sleep(wait)

        raise RuntimeError("DeepSeek call failed after all retries") from last_exc

    async def list_models(self) -> list[str]:
        try:
            resp = await self._http.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            pass
        return [self._model]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
