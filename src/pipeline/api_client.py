"""api_client.py — взаимодействие с API Минздрава РФ."""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
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


def _atomic_write_clinrecs(items: list) -> None:
    """L-60: publish clinrecs.json atomically, via a single writer.

    ``fetch_all_clinrecs`` and ``cmd_download`` both wrote this file; the first
    with a bare ``write_bytes`` (so a crash truncated the authoritative corpus
    manifest) and the second immediately overwriting it.  One helper, staged write
    plus ``os.replace``, is now the only way this file is written.
    """
    CLINRECS_JSON.parent.mkdir(parents=True, exist_ok=True)
    blob = orjson.dumps(items, option=orjson.OPT_INDENT_2)
    fd, tmp_name = tempfile.mkstemp(dir=str(CLINRECS_JSON.parent), prefix=CLINRECS_JSON.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, CLINRECS_JSON)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


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
            _atomic_write_clinrecs(all_items)
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
        _atomic_write_clinrecs(all_items)
        logger.info(f"  Total fetched: {len(all_items)} (saved to {CLINRECS_JSON})")
        return all_items

    @retry(
        stop=stop_after_attempt(RETRY_COUNT),
        wait=wait_exponential(multiplier=RETRY_BACKOFF, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ReadError, httpx.ConnectError)),
    )
    async def download_pdf(self, code_version: str, dest_path: Path) -> tuple[bool, str, str]:
        """Fetch one PDF and publish it atomically.

        L-61/L-62: the body was written with a bare ``write_bytes``, so a crash or a
        short read left a TRUNCATED file on disk -- and ``download_all_pdfs`` skips
        any destination that already exists, so that truncated file was then skipped
        FOREVER.  The bytes are now staged next to the target and moved into place
        with ``os.replace`` only after the full, PDF-magic-verified body is on disk.
        """
        url = f"{API_GET_PDF}&id={code_version}"
        resp = await self._client.get(url, follow_redirects=True)
        resp.raise_for_status()

        content = resp.content
        sha256 = hashlib.sha256(content).hexdigest()

        if not content.startswith(b"%PDF"):
            text_sample = content[:500].decode("utf-8", errors="replace")
            return False, sha256, f"Not a PDF: {text_sample}"
        if b"%%EOF" not in content[-2048:]:
            return False, sha256, "Truncated PDF: no %%EOF trailer in the last 2 KiB"

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(dest_path.parent), prefix=dest_path.name + ".", suffix=".part")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, dest_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return True, sha256, ""
