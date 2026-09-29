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


def unique_destination(
    directory: Path,
    filename: str,
    doc_id: Any = None,
    *,
    source: Path | None = None,
) -> Path:
    """Resolve a collision-free destination path for ``filename`` in ``directory``.

    H-19 / H-20 / H-24 / M-37: three writers built a target name from the guideline
    NAME alone.  Two distinct guidelines whose names sanitize to the same string
    ('Сепсис у новорождённых' vs 'Сепсис у новорождённых ', 'Отит: средний острый' vs
    'Отит  - средний острый') collided, and the second was either skipped or silently
    INHERITED the first document's path — and therefore its pdf_sha256.  Every
    downstream artifact was then anchored to the wrong PDF.

    The disambiguator is the rubricator ``Id``, which is unique per document, so the
    mapping stays stable and IDEMPOTENT across re-runs.  A numeric suffix is used
    only as a last resort when the Id-derived name is also taken.
    """
    directory = Path(directory)
    dest = directory / filename
    if not dest.exists():
        return dest

    stem, suffix = dest.stem, dest.suffix
    if doc_id not in (None, ""):
        candidate = directory / f"{stem}_{doc_id}{suffix}"
        # M-37: `candidate == dest` could never be true, so a re-run of a move that
        # had already placed the file appended another numeric suffix every time.
        # `source` makes the operation idempotent: if the file being placed IS this
        # document and it is already at the Id-derived destination, that
        # destination is the answer.
        if not candidate.exists():
            return candidate
        if source is not None and Path(source).resolve() == candidate.resolve():
            return candidate
        if source is not None and Path(source).resolve() == dest.resolve():
            return dest
        stem, dest = f"{stem}_{doc_id}", candidate

    for counter in range(2, 10_000):
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot find a free destination name for {filename!r} in {directory}")


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
            # H-19: a colliding name is disambiguated with the rubricator Id so
            # two different guidelines never share one file (and one sha256).
            dest = unique_destination(DOWNLOADS_ALL, filename, item.get("Id"))

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
