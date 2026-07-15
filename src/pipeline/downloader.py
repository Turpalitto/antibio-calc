"""downloader.py — параллельное скачивание PDF."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import orjson
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from api_client import ClinrecApi
from config import DOWNLOADS_ALL, MAX_CONCURRENT, WINDOWS_FORBIDDEN_MAP

logger = logging.getLogger(__name__)


def sanitize_filename(name: str | None) -> str:
    if not name:
        return "unnamed"
    safe = name.translate(WINDOWS_FORBIDDEN_MAP).strip()
    # collapse multiple spaces
    while "  " in safe:
        safe = safe.replace("  ", " ")
    return safe or "unnamed"


async def download_all_pdfs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Скачивает все PDF. Возвращает обогащённый список с путями к файлам."""
    DOWNLOADS_ALL.mkdir(parents=True, exist_ok=True)
    api = ClinrecApi()

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    lock = asyncio.Lock()
    results: list[dict] = []

    total = len(items)
    downloaded = 0
    skipped = 0
    failed = 0

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )

    async def _download_one(item: dict) -> dict:
        nonlocal downloaded, skipped, failed
        async with sem:
            code_version = item.get("CodeVersion", "")
            name = item.get("Name", "")
            safe_name = sanitize_filename(name)
            filename = f"{safe_name}.pdf"
            dest = DOWNLOADS_ALL / filename

            # check if already exists
            if dest.exists():
                async with lock:
                    skipped += 1
                    progress.update(task_id, advance=1, description=f"[yellow]↓[/] {skipped} skip, {failed} fail")
                return {
                    **item,
                    "pdf_path": str(dest),
                    "pdf_size": dest.stat().st_size,
                }

            try:
                ok, sha256, err = await api.download_pdf(code_version, dest)
                async with lock:
                    if ok:
                        downloaded += 1
                        progress.update(task_id, advance=1, description=f"[green]✔[/] {downloaded} ok")
                    else:
                        failed += 1
                        progress.update(task_id, advance=1, description=f"[red]✘[/] {failed} fail")
                        logger.warning(f"  PDF failed: {name} ({code_version}): {err}")
                return {
                    **item,
                    "pdf_path": str(dest) if ok else None,
                    "pdf_sha256": sha256 if ok else None,
                    "pdf_size": dest.stat().st_size if ok else None,
                    "pdf_error": err if not ok else None,
                }
            except Exception as exc:
                async with lock:
                    failed += 1
                    progress.update(task_id, advance=1, description=f"[red]✘[/] {failed} fail")
                logger.warning(f"  PDF error: {name} ({code_version}): {exc}")
                return {**item, "pdf_path": None, "pdf_error": str(exc)}

    task_id = progress.add_task("Downloading PDFs...", total=total)
    results = []

    with progress:
        tasks = [_download_one(item) for item in items]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

    results.sort(key=lambda x: x.get("Id", 0))

    await api.close()
    logger.info(f"  Total: {total}, downloaded: {downloaded}, skipped: {skipped}, failed: {failed}")
    return results
