"""Simple SHA256-based cache for LLM calls."""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


class LLMCache:
    def __init__(self, max_size: int = 512) -> None:
        # OrderedDict makes the LRU eviction O(1) instead of the previous O(n)
        # `min(self._store.items(), key=...)` scan on every insert past max_size.
        self._store: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
        self._max_size = max_size

    @staticmethod
    def make_key(
        system_prompt: str,
        user_prompt: str,
        model: str = "",
        *,
        temperature: float = 0.0,
        provider_chain: Any = None,
        **extra: Any,
    ) -> str:
        """Hash everything that can change the answer.

        The old key was ``model||system||user`` only, so two calls differing in
        temperature, in the provider chain, or in any extra kwarg collided and a
        temperature-sensitive answer could be served from a greedy one.
        """
        payload = json.dumps(
            {
                "model": model,
                "system": system_prompt,
                "user": user_prompt,
                "temperature": round(float(temperature), 6),
                "chain": list(provider_chain or []),
                "extra": {k: v for k, v in sorted(extra.items())},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._store.get(key)
        if entry is not None:
            self._store.move_to_end(key)
            logger.debug("LLM cache HIT for key %s...", key[:12])
            return entry[1]
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        elif len(self._store) >= self._max_size:
            self._store.popitem(last=False)  # evict least-recently-used, O(1)
        self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)
