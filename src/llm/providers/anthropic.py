"""Anthropic-compatible provider (vip.j3gb.com proxy)."""

import asyncio
import logging
from typing import Any

import httpx

from .base import BaseProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    def __init__(
        self,
        base_url: str = "https://vip.j3gb.com/v1",
        api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
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
        return "anthropic"

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
        max_tokens: int = 4096,
        temperature: float = 0.1,
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
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        for attempt in range(self._max_retries):
            try:
                resp = await self._http.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                # Validate response has content
                try:
                    msg = data["choices"][0]["message"]
                    if "content" not in msg or not msg["content"]:
                        raise ValueError("Empty response content")
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    logger.warning(
                        "Anthropic attempt %d/%d: empty/invalid response body, retry in %ds",
                        attempt + 1, self._max_retries, 2**attempt,
                    )
                    if attempt < self._max_retries - 1:
                        await asyncio.sleep(2**attempt)
                        continue
                    raise RuntimeError(f"Empty response after {self._max_retries} retries") from exc
                return data
            except (httpx.HTTPStatusError, httpx.RequestError, Exception) as exc:
                wait = 2**attempt
                logger.warning(
                    "Anthropic attempt %d/%d failed: %s: %s, retry in %ds",
                    attempt + 1, self._max_retries, type(exc).__name__, exc, wait,
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(wait)
                else:
                    raise

        raise RuntimeError("Anthropic call failed after all retries")

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
