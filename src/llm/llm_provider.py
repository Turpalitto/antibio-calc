"""
LLMProvider — единый интерфейс для всех LLM-вызовов в ANTIBIO.

Фичи:
- 8 бэкендов: anthropic (рабочий), deepseek, openrouter, openai, gemini, ollama, vllm, local (стенды)
- fallback-цепочка: при ошибке одного провайдера → следующий
- retry: экспоненциальный backoff внутри каждого провайдера
- кэш: SHA256(prompt) → response (не повторять одинаковые запросы)
- логирование: provider, model, время, токены, ошибки, fallback
- healthcheck, list_models, current_provider, current_model
"""

import json
import logging
import re
import time
from typing import Any

from .cache import LLMCache
from .providers import PROVIDER_MAP

logger = logging.getLogger(__name__)


class AllProvidersFailed(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = errors
        super().__init__(f"All providers failed: {errors}")


class LLMProvider:
    def __init__(
        self,
        provider_chain: list[str] | None = None,
        provider_configs: dict[str, dict] | None = None,
        cache_max_size: int = 512,
    ) -> None:
        self._provider_chain: list[str] = provider_chain or ["anthropic"]
        self._configs: dict[str, dict] = provider_configs or {}
        self._providers: dict[str, Any] = {}
        self._cache = LLMCache(max_size=cache_max_size)
        self._active_provider: str | None = None
        self._active_model: str | None = None
        self._stats: list[dict] = []

    @property
    def current_provider(self) -> str | None:
        return self._active_provider

    @property
    def current_model(self) -> str | None:
        return self._active_model

    def _get_provider(self, name: str) -> Any:
        if name not in self._providers:
            cls = PROVIDER_MAP.get(name)
            if cls is None:
                raise ValueError(f"Unknown provider: {name}")
            cfg = self._configs.get(name, {})
            self._providers[name] = cls(**cfg)
        return self._providers[name]

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.1,
        **extra_kwargs: Any,
    ) -> str:
        result = await self.chat(system_prompt, user_prompt, model, temperature=temperature, **extra_kwargs)
        return result["choices"][0]["message"]["content"]

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.1,
        **extra_kwargs: Any,
    ) -> dict | list:
        text = await self.generate(system_prompt, user_prompt, model, temperature=temperature, **extra_kwargs)
        return self._parse_json(text)

    @staticmethod
    def _parse_json(content: str) -> dict | list:
        content = content.strip()
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if fence_match:
            content = fence_match.group(1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            for start, end in [("[", "]"), ("{", "}")]:
                s = content.find(start)
                e = content.rfind(end)
                if s != -1 and e != -1 and e > s:
                    return json.loads(content[s : e + 1])
            raise

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.1,
        **extra_kwargs: Any,
    ) -> dict[str, Any]:
        cache_key = self._cache.make_key(system_prompt, user_prompt, model or "")
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for prompt (key=%s)", cache_key[:12])
            return cached

        errors: list[tuple[str, str]] = []
        t0 = time.monotonic()

        for provider_name in self._provider_chain:
            provider = self._get_provider(provider_name)
            try:
                resp = await provider.chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    temperature=temperature,
                    **extra_kwargs,
                )
                elapsed = time.monotonic() - t0
                self._active_provider = provider_name
                self._active_model = resp.get("model", model or provider.default_model)
                self._log_call(provider_name, self._active_model, elapsed, resp, errors)
                self._cache.set(cache_key, resp)
                return resp
            except NotImplementedError:
                errors.append((provider_name, "not implemented (stub)"))
                continue
            except Exception as exc:
                elapsed = time.monotonic() - t0
                err_str = f"{type(exc).__name__}: {exc}"
                errors.append((provider_name, err_str))
                logger.warning(
                    "Provider %s failed in %.1fs: %s. %s",
                    provider_name, elapsed, err_str,
                    "Trying next..." if provider_name != self._provider_chain[-1] else "No more providers.",
                )
                continue

        raise AllProvidersFailed(errors)

    def _log_call(
        self,
        provider: str,
        model: str,
        elapsed: float,
        response: dict,
        errors: list[tuple[str, str]],
    ) -> None:
        usage = response.get("usage", {})
        tokens = {
            "prompt": usage.get("prompt_tokens", 0),
            "completion": usage.get("completion_tokens", 0),
            "total": usage.get("total_tokens", 0),
        }
        entry = {
            "timestamp": time.time(),
            "provider": provider,
            "model": model,
            "elapsed_sec": round(elapsed, 2),
            "tokens": tokens,
            "fallback_count": len(errors),
        }
        self._stats.append(entry)
        logger.info(
            "LLM call: provider=%s model=%s elapsed=%.1fs tokens=%d errors=%d",
            provider, model, elapsed, tokens["total"], len(errors),
        )

    async def healthcheck(self) -> bool:
        for provider_name in self._provider_chain:
            provider = self._get_provider(provider_name)
            try:
                ok = await provider.healthcheck()
                if ok:
                    self._active_provider = provider_name
                    self._active_model = provider.default_model
                    logger.info("Healthcheck OK: %s/%s", provider_name, provider.default_model)
                    return True
            except NotImplementedError:
                continue
            except Exception as exc:
                logger.warning("Healthcheck failed for %s: %s", provider_name, exc)
                continue
        logger.error("Healthcheck: all providers failed")
        return False

    async def list_models(self) -> list[str]:
        models: list[str] = []
        for provider_name in self._provider_chain:
            provider = self._get_provider(provider_name)
            try:
                models.extend(await provider.list_models())
            except Exception:
                models.append(f"{provider_name}/{provider.default_model}")
        return models

    def stats(self) -> list[dict]:
        return list(self._stats)

    def stats_summary(self) -> dict:
        total_calls = len(self._stats)
        if not total_calls:
            return {"calls": 0}
        total_tokens = sum(s["tokens"]["total"] for s in self._stats)
        total_elapsed = sum(s["elapsed_sec"] for s in self._stats)
        return {
            "calls": total_calls,
            "total_tokens": total_tokens,
            "total_elapsed_sec": round(total_elapsed, 1),
            "avg_elapsed_sec": round(total_elapsed / total_calls, 2) if total_calls else 0,
            "active_provider": self._active_provider,
            "active_model": self._active_model,
        }

    async def close(self) -> None:
        for name, provider in self._providers.items():
            try:
                await provider.close()
            except Exception:
                pass


def create_provider(
    chain: list[str] | None = None,
    configs: dict[str, dict] | None = None,
) -> LLMProvider:
    """Factory: creates LLMProvider from pipeline config."""
    if chain is None:
        try:
            from config import LLM_PROVIDER_CHAIN  # noqa: PLC0415
            chain = LLM_PROVIDER_CHAIN
        except ImportError:
            chain = ["anthropic"]
    if configs is None:
        try:
            from config import LLM_PROVIDER_CONFIGS  # noqa: PLC0415
            configs = LLM_PROVIDER_CONFIGS
        except ImportError:
            configs = {}
    remote_providers = {"anthropic", "deepseek", "gemini", "openai", "openrouter"}
    missing = [
        name
        for name in chain
        if name in remote_providers and not str(configs.get(name, {}).get("api_key", "")).strip()
    ]
    if missing:
        variables = ", ".join(f"ANTIBIO_{name.upper()}_API_KEY" for name in missing)
        raise RuntimeError(f"Missing required LLM credentials: {variables}")
    return LLMProvider(provider_chain=chain, provider_configs=configs)
