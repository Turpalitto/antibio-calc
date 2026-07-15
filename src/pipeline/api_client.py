"""api_client.py — взаимодействие с API Минздрава РФ."""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import orjson
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import (
    API_GET_PDF,
    API_LIST,
    CLINRECS_JSON,
    DOWNLOADS_ALL,
    MAX_CONCURRENT,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF,
    RETRY_COUNT,
)

logger = logging.getLogger(__name__)


def _default_json(data: dict) -> bytes:
    return orjson.dumps(data)


class ClinrecApi:
    def __init__(self) -> None:
        limits = httpx.Limits(
            max_connections=MAX_CONCURRENT + 5,
            max_keepalive_connections=MAX_CONCURRENT,
        )
        self._client = httpx.AsyncClient(
            base_url="",
            timeout=httpx.Timeout(REQUEST_TIMEOUT, connect=15.0),
            limits=limits,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(RETRY_COUNT),
        wait=wait_exponential(multiplier=RETRY_BACKOFF, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ReadError, httpx.ConnectError)),
    )
    async def _post(self, url: str, json_data: dict) -> httpx.Response:
        resp = await self._client.post(url, content=orjson.dumps(json_data))
        resp.raise_for_status()
        return resp

    async def fetch_all_clinrecs(
        self,
        page_size: int = 200,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        logger.info(f"Fetching clinical recommendations (pageSize={page_size})...")

        # first call to get TotalRecords
        resp = await self._post(API_LIST, {"CurrentPage": 0, "PageSize": 1})
        data: dict = orjson.loads(resp.content)
        total = int(data.get("TotalRecords", 0))
        logger.info(f"  TotalRecords = {total}")

        all_items: list[dict] = []

        # try big page
        resp = await self._post(API_LIST, {"CurrentPage": 0, "PageSize": page_size})
        data = orjson.loads(resp.content)
        first_page_items = data.get("Data", [])
        all_items.extend(first_page_items)
        page_count = (total + page_size - 1) // page_size
        logger.info(f"  Pages needed (at pageSize={page_size}): {page_count}")

        if page_count <= 1:
            logger.info(f"  All {len(all_items)} records in one page")
            CLINRECS_JSON.write_bytes(orjson.dumps(all_items, option=orjson.OPT_INDENT_2))
            return all_items

        if max_pages and page_count > max_pages:
            page_count = max_pages

        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def _fetch_page(page: int) -> list[dict]:
            async with sem:
                try:
                    resp = await self._post(API_LIST, {
                        "CurrentPage": page,
                        "PageSize": page_size,
                    })
                    page_data: dict = orjson.loads(resp.content)
                    return page_data.get("Data", [])
                except Exception as exc:
                    logger.warning(f"  Page {page} failed: {exc}")
                    return []

        tasks = [_fetch_page(p) for p in range(1, page_count)]
        for coro in asyncio.as_completed(tasks):
            items = await coro
            if items:
                all_items.extend(items)

        all_items.sort(key=lambda x: x.get("Id", 0))
        CLINRECS_JSON.write_bytes(orjson.dumps(all_items, option=orjson.OPT_INDENT_2))
        logger.info(f"  Total fetched: {len(all_items)} (saved to {CLINRECS_JSON})")
        return all_items

    @retry(
        stop=stop_after_attempt(RETRY_COUNT),
        wait=wait_exponential(multiplier=RETRY_BACKOFF, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ReadError, httpx.ConnectError)),
    )
    async def download_pdf(self, code_version: str, dest_path: Path) -> tuple[bool, str, str]:
        url = f"{API_GET_PDF}&id={code_version}"
        resp = await self._client.get(url, follow_redirects=True)
        resp.raise_for_status()

        content = resp.content
        sha256 = hashlib.sha256(content).hexdigest()

        if not content.startswith(b"%PDF"):
            text_sample = content[:500].decode("utf-8", errors="replace")
            return False, sha256, f"Not a PDF: {text_sample}"

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(content)
        return True, sha256, ""
