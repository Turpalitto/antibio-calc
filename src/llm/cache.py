"""Simple SHA256-based cache for LLM calls."""

import hashlib
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class LLMCache:
    def __init__(self, max_size: int = 512) -> None:
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}
        self._max_size = max_size

    @staticmethod
    def make_key(system_prompt: str, user_prompt: str, model: str = "") -> str:
        raw = f"{model}||{system_prompt}||{user_prompt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._store.get(key)
        if entry is not None:
            logger.debug("LLM cache HIT for key %s...", key[:12])
            return entry[1]
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if len(self._store) >= self._max_size:
            oldest = min(self._store.items(), key=lambda x: x[1][0])
            del self._store[oldest[0]]
        self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)
