#!/usr/bin/env python3
"""main.py — CLI для загрузки, анализа и фильтрации клинических рекомендаций."""

import argparse
import asyncio
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from hashlib import sha256 as _sha256
from pathlib import Path
from typing import Any

import httpx
import orjson
from rich.console import Console
from rich.logging import RichHandler


# L-5: there were TWO locks for the same file -- a module-level ``_write_lock`` and
# the ``save_lock`` created inside cmd_extract_raw -- and only one of them was ever
# used.  A module-level asyncio.Lock is additionally bound to the first event loop
# that awaits it, so it is unsafe across successive asyncio.run() invocations.  The
# single per-command lock below is the only one, and _safe_write no longer needs one
# because os.replace makes the publish step atomic.


async def _safe_write(path: Path, data: list) -> None:
    """Atomic, crash-safe JSON list write with an integrity check.

    H-4: the old implementation truncate-wrote the authoritative file in place, so
    a crash mid-write left a truncated ``extraction_raw.json``.  The payload is now
    staged next to the target and moved into place with :func:`os.replace`, which is
    atomic on POSIX and Windows, then re-read and verified.  The docstring's
    "no atomic rename (too fragile on Windows)" claim was the bug, not the fix.
    """
    blob = orjson.dumps(data, option=orjson.OPT_INDENT_2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        # Verify the staged bytes BEFORE they become authoritative.
        back = orjson.loads(tmp.read_bytes())
        if not isinstance(back, list):
            raise RuntimeError("Write corruption: not a list")
        if len(back) < len(data):
            raise RuntimeError(f"Write corruption: expected >= {len(data)}, got {len(back)}")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise




# C-4/C-5: `main.py` used only flat (`from config import ...`) imports, so the
# module could not be imported as part of the `src.pipeline` package at all --
# which is precisely why the positional-pairs bug in cmd_validate had no test.
# Relative imports are canonical; the flat form is kept for the legacy
# `cd src/pipeline && python main.py <cmd>` invocation.
try:  # package import: `python -m src.pipeline.main`, pytest
    from .api_client import ClinrecApi
    from .analyzer import analyze_one
    from .antibiotic_gate import gate_one
    from .classifier import classify_one
    from .config import (
        BASE_DIR,
        CLINRECS_JSON,
        DOWNLOADS_ACTIVE,
        EXTRACTION_MODEL,
        EXTRACTION_RAW_JSON,
        EXTRACTION_VALIDATED_JSON,
        EXTRACTION_VERSION,
        KNOWLEDGE_BASE_JSON,
        LLM_CONCURRENCY,
        LLM_DELAY,
        LLM_PROVIDER_CHAIN,
        REVIEW_REQUIRED_JSON,
        VALIDATION_MODEL,
    )
    from .database import (
        init_regimens_table,
        save_antibiotic_json,
        save_metadata,
        save_regimens,
        split_by_category,
    )
    from .downloader import download_all_pdfs
    from .extractor_llm import (
        check_source_fields,
        extract_regimens,
        source_quote_supported,
        validate_regimens,
    )
    from .progress import (
        get_pending_items,
        load_progress,
        mark_extraction_done,
        mark_extraction_incomplete,
        mark_validation_done,
        needs_reprocessing,
        save_progress,
    )
    from .reporter import generate_report
    from .section_detector import detect_sections
except ImportError:  # pragma: no cover - legacy `cd src/pipeline && python main.py`
    from api_client import ClinrecApi
    from analyzer import analyze_one
    from antibiotic_gate import gate_one
    from classifier import classify_one
    from config import (
        BASE_DIR,
        CLINRECS_JSON,
        DOWNLOADS_ACTIVE,
        EXTRACTION_MODEL,
        EXTRACTION_RAW_JSON,
        EXTRACTION_VALIDATED_JSON,
        EXTRACTION_VERSION,
        KNOWLEDGE_BASE_JSON,
        LLM_CONCURRENCY,
        LLM_DELAY,
        LLM_PROVIDER_CHAIN,
        REVIEW_REQUIRED_JSON,
        VALIDATION_MODEL,
    )
    from database import (
        init_regimens_table,
        save_antibiotic_json,
        save_metadata,
        save_regimens,
        split_by_category,
    )
    from downloader import download_all_pdfs
    from extractor_llm import (
        check_source_fields,
        extract_regimens,
        source_quote_supported,
        validate_regimens,
    )
    from progress import (
        get_pending_items,
        load_progress,
        mark_extraction_done,
        mark_extraction_incomplete,
        mark_validation_done,
        needs_reprocessing,
        save_progress,
    )
    from reporter import generate_report
    from section_detector import detect_sections
except ModuleNotFoundError as _exc:  # legacy flat import
    if _exc.name not in ("config", "api_client", "analyzer", "antibiotic_gate",
                         "classifier", "database", "downloader", "extractor_llm",
                         "progress", "reporter", "section_detector"):
        # A MISSING transitive dependency is a real error, not "we are being
        # imported flat".  B025: swallowing it here would mask a broken install.
        raise
    from api_client import ClinrecApi
    from analyzer import analyze_one
    from antibiotic_gate import gate_one
    from classifier import classify_one
    from config import (
        BASE_DIR,
        CLINRECS_JSON,
        DOWNLOADS_ACTIVE,
        EXTRACTION_MODEL,
        EXTRACTION_RAW_JSON,
        EXTRACTION_VALIDATED_JSON,
        EXTRACTION_VERSION,
        KNOWLEDGE_BASE_JSON,
        LLM_CONCURRENCY,
        LLM_DELAY,
        LLM_PROVIDER_CHAIN,
        REVIEW_REQUIRED_JSON,
        VALIDATION_MODEL,
    )
    from database import (
        init_regimens_table,
        save_antibiotic_json,
        save_metadata,
        save_regimens,
        split_by_category,
    )
    from downloader import download_all_pdfs
    from extractor_llm import (
        check_source_fields,
        extract_regimens,
        source_quote_supported,
        validate_regimens,
    )
    from progress import (
        get_pending_items,
        load_progress,
        mark_extraction_done,
        mark_extraction_incomplete,
        mark_validation_done,
        needs_reprocessing,
        save_progress,
    )
    from reporter import generate_report
from section_detector import detect_sections

console = Console()
logger = logging.getLogger("clinrec")

LOG_FMT = "%(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FMT,
    datefmt="[%H:%M:%S]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)


def _load_items() -> list[dict]:
    if not CLINRECS_JSON.exists():
        console.print(f"[red]File not found: {CLINRECS_JSON}[/]")
        console.print("Run [bold]download[/] first.")
        sys.exit(1)
    items = orjson.loads(CLINRECS_JSON.read_bytes())
    for item in items:
        pp = item.get("pdf_path", "")
        if pp and not Path(pp).is_absolute():
            resolved = str(Path(BASE_DIR) / pp)
            # Check if file was moved to downloads_active by prefilter
            fname = Path(pp).name
            active_path = DOWNLOADS_ACTIVE / fname
            if active_path.exists():
                resolved = str(active_path)
            item["pdf_path"] = resolved
    return items


async def cmd_download(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE 1+2: Download all PDFs[/]\n")
    api = ClinrecApi()
    try:
        items = await api.fetch_all_clinrecs(page_size=args.page_size)
    finally:
        await api.close()

    console.print(f"\n[bold]Fetched {len(items)} clinical recommendations.[/]")
    console.print("[bold]Starting PDF download...[/]\n")

    enriched = await download_all_pdfs(items)

    # save intermediate results
    CLINRECS_JSON.write_bytes(orjson.dumps(enriched, option=orjson.OPT_INDENT_2))

    ok = sum(1 for i in enriched if i.get("pdf_path"))
    fail = len(enriched) - ok
    console.print(f"\n[bold]Download complete: {ok} OK, {fail} failed[/]")


async def cmd_analyze(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE 3+4+5: Text extraction + antibiotic detection[/]\n")
    items = _load_items()

    analyzed: list[dict] = []
    abx_count = 0
    t0 = time.monotonic()

    for i, item in enumerate(items):
        if (i + 1) % 50 == 0 or i == 0:
            console.print(f"  Analyzing {i + 1}/{len(items)}... (found {abx_count} with antibiotics)")
        result = analyze_one(item)
        if result.get("has_antibiotics"):
            abx_count += 1
        analyzed.append(result)

    elapsed = time.monotonic() - t0
    console.print(f"\n  Analyzed {len(analyzed)} in {elapsed:.1f}s")
    console.print(f"  With antibiotics: [green]{abx_count}[/]")

    CLINRECS_JSON.write_bytes(orjson.dumps(analyzed, option=orjson.OPT_INDENT_2))


async def cmd_filter(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE 6: Split into antibiotics / other[/]\n")
    items = _load_items()
    items = split_by_category(items)

    abx = sum(1 for i in items if i.get("category") == "antibiotics")
    other = sum(1 for i in items if i.get("category") == "other")
    console.print(f"  antibiotics: [green]{abx}[/]")
    console.print(f"  other:       [dim]{other}[/]")

    CLINRECS_JSON.write_bytes(orjson.dumps(items, option=orjson.OPT_INDENT_2))


async def cmd_classify(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE: A/B/C/D Classification[/]\n")
    items = _load_items()

    classified: list[dict] = []
    level_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    t0 = time.monotonic()

    for i, item in enumerate(items):
        if (i + 1) % 50 == 0 or i == 0:
            console.print(f"  Classifying {i + 1}/{len(items)}... A={level_counts['A']} B={level_counts['B']} C={level_counts['C']} D={level_counts['D']}")
        result = classify_one(item)
        level_counts[result["abx_level"]] = level_counts.get(result["abx_level"], 0) + 1
        classified.append(result)

    elapsed = time.monotonic() - t0
    console.print(f"\n  Classified {len(classified)} in {elapsed:.1f}s")
    for level in ["A", "B", "C", "D"]:
        console.print(f"  Level {level}: [green]{level_counts[level]}[/]")

    review_items = []
    for item in classified:
        if item.get("abx_level") == "C":
            review_items.append({
                "clinrec_id": item.get("Id"),
                "guideline_name": item.get("Name"),
                "code_version": item.get("CodeVersion"),
                "pdf_file": item.get("pdf_path", "").split("\\")[-1].split("/")[-1] if item.get("pdf_path") else "",
                "abx_level": "C",
                "reason": "level_c_keyword_only",
                "confidence": item.get("confidence_score", 0) / 100.0,
                "page_number": "",
                "section_name": "",
                "extracted_data": {},
                "expected_fix": "Review manually: keyword mentions only, no treatment section found",
                "validation_issues": [],
            })

    from database import save_review_required
    save_review_required(review_items, REVIEW_REQUIRED_JSON)
    console.print(f"  Review required: {len(review_items)} items")

    CLINRECS_JSON.write_bytes(orjson.dumps(classified, option=orjson.OPT_INDENT_2))


async def cmd_gate(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE: Antibiotic Gate[/]\n")
    items = _load_items()

    from extractor import extract_text
    from pathlib import Path as _Path

    results: list[dict] = []
    status_counts = {"process": 0, "review": 0, "skip": 0}
    t0 = time.monotonic()

    for i, item in enumerate(items):
        if (i + 1) % 100 == 0 or i == 0:
            console.print(f"  Gating {i + 1}/{len(items)}... process={status_counts['process']} review={status_counts['review']} skip={status_counts['skip']}")

        pdf_path_str = item.get("pdf_path", "")
        pdf_text = ""
        if pdf_path_str and _Path(pdf_path_str).exists():
            pdf_text = extract_text(_Path(pdf_path_str)) or ""

        result = gate_one(item, pdf_text)
        results.append(result)
        status_counts[result["status"]] += 1

    elapsed = time.monotonic() - t0
    console.print(f"\n  Gated {len(results)} in {elapsed:.1f}s")
    for s in ["process", "review", "skip"]:
        console.print(f"  {s}: [green]{status_counts[s]}[/]")

    process_list = [r for r in results if r["status"] == "process"]
    review_list = [r for r in results if r["status"] == "review"]
    skip_list = [r for r in results if r["status"] == "skip"]

    import json as _json
    BASE = _Path(__file__).resolve().parent

    _p = BASE / "antibiotic_filter.json"
    _p.write_text(_json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"  antibiotic_filter.json: {len(results)} records")

    _p = BASE / "antibiotic_candidates.json"
    _p.write_text(_json.dumps(process_list, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"  antibiotic_candidates.json: {len(process_list)} records (process)")

    _p = BASE / "review_required.json"
    _p.write_text(_json.dumps(review_list, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"  review_required.json: {len(review_list)} records (review)")

    _p = BASE / "skipped_guidelines.json"
    _p.write_text(_json.dumps(skip_list, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"  skipped_guidelines.json: {len(skip_list)} records (skip)")


async def cmd_extract_raw(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE: LLM Extraction (DeepSeek V4 Pro)[/]\n")
    items = _load_items()

    extractable = [i for i in items if i.get("abx_level") in ("A", "B")]
    console.print(f"  Level A+B items: {len(extractable)}")

    if args.force:
        pending = extractable
    else:
        # Use progress file to skip done items
        pending = get_pending_items(extractable)
        # Also skip items already in extraction_raw.json (safety net)
        if EXTRACTION_RAW_JSON.exists() and EXTRACTION_RAW_JSON.stat().st_size > 100:
            try:
                existing_raw = orjson.loads(EXTRACTION_RAW_JSON.read_bytes())
                if isinstance(existing_raw, list):
                    raw_ids = {r.get("clinrec_id", 0) for r in existing_raw if r.get("clinrec_id")}
                    # Filter out items that are already in raw output
                    # but NOT in progress (e.g., from a previous --force run)
                    pending = [i for i in pending if i.get("Id", 0) not in raw_ids]
            except Exception:
                pass

    if args.limit and len(pending) > args.limit:
        pending = pending[:args.limit]

    console.print(f"  Pending extraction: {len(pending)}")

    if not pending:
        console.print("  [green]Nothing to extract[/]")
        return

    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    save_lock = asyncio.Lock()
    failed: list[dict] = []
    # H-4: keep the accumulated payload in memory and flush in batches instead of
    # re-reading, re-parsing, re-serialising and truncate-writing the whole file on
    # EVERY completed PDF (O(n^2) over the corpus).  The file still holds the last
    # flushed checkpoint on a hard crash, and every flush is now an atomic
    # os.replace, so the authoritative file is never truncated.
    pending: list[dict] = []
    flushed = 0
    FLUSH_EVERY = 10
    t0 = time.monotonic()
    processed_count = 0
    regimen_count = 0
    checkpoint_counter = 0
    checkpoint_t0 = time.monotonic()

    async def _flush(force: bool = False) -> None:
        nonlocal flushed
        if not pending or (not force and len(pending) < FLUSH_EVERY):
            return
        async with save_lock:
            batch, pending[:] = list(pending), []
            existing = []
            if EXTRACTION_RAW_JSON.exists():
                try:
                    existing = orjson.loads(EXTRACTION_RAW_JSON.read_bytes())
                    if not isinstance(existing, list):
                        existing = []
                except Exception:
                    logger.error("Corrupted extraction_raw.json — recovery needed")
                    raise
            existing.extend(batch)
            await _safe_write(EXTRACTION_RAW_JSON, existing)
            flushed += len(batch)

    async def _save_incremental(regimens: list[dict]) -> None:
        """Stage extracted regimens; the file is rewritten atomically per batch."""
        pending.extend(regimens)
        await _flush()

    async def process_one(item: dict) -> None:
        # `checkpoint_t0` must be non-local: assigning it here without `nonlocal`
        # made it a LOCAL of process_one, so the read a few lines above raised
        # UnboundLocalError on the 10th completed document.
        nonlocal failed, processed_count, regimen_count, checkpoint_counter, checkpoint_t0
        async with semaphore:
            pdf_path = item.get("pdf_path", "")
            if not pdf_path or not Path(pdf_path).exists():
                return

            pdf_sha256 = _sha256(Path(pdf_path).read_bytes()).hexdigest()
            clinrec_id = item.get("Id", 0)

            if not args.force and not needs_reprocessing(clinrec_id, pdf_sha256):
                return

            section_data = detect_sections(Path(pdf_path), clinrec_id=clinrec_id)
            if not section_data.get("relevant_text"):
                # H-3: recorded as an explicit incomplete outcome, never as success.
                mark_extraction_incomplete(clinrec_id, pdf_sha256, "no_relevant_text")
                processed_count += 1
                console.print(f"  [{clinrec_id}] no relevant text — NOT marked done (retryable)")
                return

            try:
                regimens = await extract_regimens(item, section_data)
                if not regimens:
                    # Same reasoning as above: an empty LLM answer is a failed
                    # extraction, not a document that contains no antibiotics.
                    mark_extraction_incomplete(clinrec_id, pdf_sha256, "zero_regimens")
                    processed_count += 1
                    console.print(f"  [{clinrec_id}] {item.get('Name', '')[:40]}: 0 regimens — NOT marked done")
                    return

                for r in regimens:
                    r["clinrec_id"] = clinrec_id
                    r["clinrec_name"] = item.get("Name", "")
                    r["pdf_sha256"] = pdf_sha256
                    r["publication_date"] = item.get("PublishDateStr", "")
                    r["extraction_version"] = EXTRACTION_VERSION
                    r["extraction_model"] = EXTRACTION_MODEL
                    r["extracted_at"] = datetime.now(timezone.utc).isoformat()
                    if not check_source_fields(r):
                        r["_missing_source"] = True

                # Save incrementally with integrity check
                await _save_incremental(regimens)

                # Only now mark as done (after successful save + verify)
                mark_extraction_done(clinrec_id, pdf_sha256, len(regimens))
                processed_count += 1
                regimen_count += len(regimens)
                checkpoint_counter += 1
                console.print(f"  [{clinrec_id}] {item.get('Name', '')[:40]}: {len(regimens)} regimens")

                # Every-10 checkpoint with stats
                if checkpoint_counter % 10 == 0:
                    cp_elapsed = time.monotonic() - checkpoint_t0
                    rate = 10 / cp_elapsed if cp_elapsed > 0 else 0
                    total_elapsed = time.monotonic() - t0
                    console.print(f"  [dim]╚═ CHECKPOINT {checkpoint_counter}: {processed_count} PDFs, {regimen_count} regimens, {rate:.1f} PDF/s, {total_elapsed:.0f}s total[/]")
                    checkpoint_t0 = time.monotonic()
            except Exception as exc:
                failed.append({"clinrec_id": clinrec_id, "name": item.get("Name"), "error": str(exc)})
                logger.warning(f"  Extraction failed for {clinrec_id}: {exc}")

    tasks = [process_one(item) for item in pending]
    await asyncio.gather(*tasks)

    # Final flush so a partial batch is never left only in memory.
    await _flush(force=True)

    elapsed = time.monotonic() - t0
    console.print(f"\n  Processed {processed_count} PDFs, extracted {regimen_count} regimens in {elapsed:.1f}s")
    if checkpoint_counter >= 10:
        console.print(f"  Final checkpoint: {checkpoint_counter} checkpoints written")
    if failed:
        console.print(f"  [red]Failed: {len(failed)}[/]")
    console.print(f"  Saved to {EXTRACTION_RAW_JSON} (incremental, UNVALIDATED) — {flushed} regimens flushed")
    console.print(f"  Progress: {EXTRACTION_RAW_JSON.with_name('extraction_progress.json')} (atomic fsync per checkpoint)")


async def cmd_validate(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE: GLM 5.2 Validation[/]\n")

    if not EXTRACTION_RAW_JSON.exists():
        console.print(f"[red]File not found: {EXTRACTION_RAW_JSON}[/]")
        console.print("Run [bold]extract_raw[/] first.")
        return

    raw_regimens = orjson.loads(EXTRACTION_RAW_JSON.read_bytes())
    console.print(f"  Raw regimens: {len(raw_regimens)}")

    if not raw_regimens:
        console.print("  [yellow]No regimens to validate[/]")
        return

    from collections import defaultdict
    by_clinrec = defaultdict(list)
    for r in raw_regimens:
        by_clinrec[r.get("clinrec_id", 0)].append(r)

    validated: list[dict] = []
    review_items: list[dict] = []
    t0 = time.monotonic()

    items_map = {i.get("Id"): i for i in _load_items()}
    prog_data = load_progress()

    for clinrec_id, regimens in by_clinrec.items():
        # Skip if already validated (progress check)
        prog_entry = prog_data["items"].get(str(clinrec_id), {})
        if prog_entry.get("validation_done"):
            continue

        item = items_map.get(clinrec_id, {})
        pdf_path = item.get("pdf_path", "")
        section_data = detect_sections(Path(pdf_path), clinrec_id=clinrec_id) if pdf_path else {}

        try:
            results = await validate_regimens(regimens, section_data)
        except Exception as exc:
            logger.warning(f"  Validation failed for {clinrec_id}: {exc}")
            for idx, r in enumerate(regimens):
                review_items.append(_review_item(
                    clinrec_id, item, r, r,
                    reason="validation_api_error", confidence=0.0,
                    issues=[str(exc)],
                    expected_fix=f"Validation API error: {exc}",
                ))
            continue

        # H-5: an EMPTY result list must never be recorded as "validated done".
        # It means nothing was processed, so the guideline stays pending and the
        # next run retries it.  The old code marked it done, permanently dropping
        # every regimen for that guideline.
        if not results:
            review_items.extend(
                _review_item(
                    clinrec_id, item, r, r,
                    reason="validation_returned_no_results", confidence=0.0,
                    issues=["LLM returned no validation results"],
                    expected_fix="Re-run validation: the validator returned no verdicts for this guideline",
                )
                for r in regimens
            )
            console.print(
                f"  [yellow][{clinrec_id}] validator returned 0 results — not marked done "
                f"({len(regimens)} regimens queued for review)[/]"
            )
            continue

        # C-4: pair each verdict with the regimen it names via result["index"].
        # Pairing POSITIONALLY (enumerate) silently attached a verdict -- and its
        # `corrected` payload -- to the wrong regimen whenever the model reordered,
        # omitted or inserted a result.  Pairing by index also means a surplus
        # regimen keeps its own data instead of landing in review as {}.
        for idx, result in enumerate(results):
            position, pairing_problem = _resolve_result_index(result, idx, len(regimens))
            if position is None:
                review_items.append(_review_item(
                    clinrec_id, item, regimens[idx], regimens[idx],
                    reason="validation_result_index_invalid",
                    confidence=float(result.get("confidence", 0.0) or 0.0),
                    issues=list(result.get("issues") or []) + [pairing_problem],
                    expected_fix=pairing_problem,
                ))
                continue
            regimen = regimens[position]
            confidence = result.get("confidence", 0.0)
            valid = result.get("valid", False)
            issues = result.get("issues", [])
            corrected, correction_problem = _validated_correction(
                result.get("corrected"), regimen, section_data,
            )
            if correction_problem:
                # C-5: a correction the validator could not justify means the whole
                # verdict is untrustworthy.  Promoting it to validated=1 anyway would
                # launder a rejected edit into the trusted output file.
                issues = list(issues) + [correction_problem]
                corrected = None
                valid = False
                confidence = min(float(confidence or 0.0), 0.0)

            if corrected and valid:
                regimen = {**regimen, **corrected}

            if regimen.get("_missing_source"):
                review_items.append(_review_item(
                    clinrec_id, item, regimen, regimen,
                    reason="missing_source_evidence", confidence=confidence,
                    issues=issues,
                    expected_fix="Add missing source fields (guideline_name, code_version, pdf_file, page_number, section_name, source_quote)",
                ))
            elif valid and confidence >= 0.9:
                regimen["validation_confidence"] = confidence
                regimen["validation_issues"] = issues
                regimen["validated"] = 1
                regimen["validation_model"] = VALIDATION_MODEL
                regimen["validated_at"] = datetime.now(timezone.utc).isoformat()
                validated.append(regimen)
            else:
                review_items.append(_review_item(
                    clinrec_id, item, regimen, regimen,
                    reason="validation_failed", confidence=confidence,
                    issues=issues,
                    expected_fix="; ".join(str(i) for i in issues) if issues else "Confidence below 0.9",
                ))

        # C-4: any regimen the validator never mentioned keeps its own data and goes
        # to review -- it is never silently dropped and never mis-paired.
        covered = {r for r in _result_indices(results, len(regimens)) if r is not None}
        for position, orphan in enumerate(regimens):
            if position in covered:
                continue
            review_items.append(_review_item(
                clinrec_id, item, orphan, orphan,
                reason="validation_result_missing", confidence=0.0,
                issues=[f"no validation result carried index {position}"],
                expected_fix=f"Re-validate: the validator returned no verdict for regimen #{position}",
            ))

        mark_validation_done(clinrec_id, min((r.get("confidence", 0) for r in results), default=0.0))

    elapsed = time.monotonic() - t0
    console.print(f"\n  Validated: {len(validated)} regimens")
    console.print(f"  Review required: {len(review_items)} regimens")
    console.print(f"  Time: {elapsed:.1f}s")

    EXTRACTION_VALIDATED_JSON.write_bytes(orjson.dumps(validated, option=orjson.OPT_INDENT_2))
    console.print(f"  Saved to {EXTRACTION_VALIDATED_JSON}")

    existing_review = []
    if REVIEW_REQUIRED_JSON.exists():
        existing_review = orjson.loads(REVIEW_REQUIRED_JSON.read_bytes())
    from database import save_review_required
    # H-2 / M-41: save_review_required dedups, so re-running `validate` on a
    # partially-completed corpus no longer appends a fresh copy of every item.
    save_review_required(existing_review + review_items, REVIEW_REQUIRED_JSON)
    console.print(f"  Updated {REVIEW_REQUIRED_JSON} ({len(existing_review) + len(review_items)} submitted, deduped on write)")


def _result_indices(results: list, n_regimens: int) -> list[int | None]:
    """Map every result onto the regimen index it names (None when unusable)."""
    return [_resolve_result_index(r, i, n_regimens)[0] for i, r in enumerate(results)]


def _resolve_result_index(result: dict, position: int, n_regimens: int) -> tuple[int | None, str]:
    """Resolve the regimen index a validation result refers to.

    C-4: the prompt asks the model for an explicit ``index`` and the code never
    read it.  Anything missing, non-integer, or out of range is reported as a
    problem instead of being paired with `regimens[position]`, which silently
    stamped a verdict (and its `corrected` payload) onto the wrong regimen.
    """
    if not isinstance(result, dict):
        return None, f"validation result #{position} is not an object"
    if "index" not in result:
        return None, (
            f"validation result #{position} has no 'index'; refusing to guess which "
            f"regimen it refers to"
        )
    raw = result.get("index")
    if isinstance(raw, bool) or not isinstance(raw, int):
        try:
            raw = int(str(raw).strip())
        except (TypeError, ValueError):
            return None, f"validation result #{position} has a non-integer index {raw!r}"
    if raw < 0 or raw >= n_regimens:
        return None, f"validation result #{position} has out-of-range index {raw} (regimens: {n_regimens})"
    return raw, ""


# C-5: fields the validator is never allowed to invent, whatever `valid` says.
_FORBIDDEN_CORRECTION_FIELDS = frozenset({
    # identity + provenance locators: nothing can verify these against the source,
    # so the validator is never allowed to rewrite them
    "pdf_sha256", "clinrec_id", "pdf_file", "guideline_name", "code_version",
    "page_number", "section_name",
    # validation stamping: the validator must not be able to mark itself correct
    "validated", "validation_confidence", "validation_model", "validated_at",
    "extraction_model", "extraction_version", "extracted_at",
})


def _validated_correction(corrected: Any, regimen: dict, section_data: dict) -> tuple[dict | None, str]:
    """Validate an LLM ``corrected`` payload before it is merged over a regimen.

    C-5: the old code did ``regimen = {**regimen, **corrected}`` and then
    ``regimen["validated"] = 1`` on the strength of a boolean the same LLM
    supplied.  A hallucinated quote or dose was therefore promoted straight into
    ``extraction_validated.json`` -- the file every downstream stage trusts.

    A correction is accepted only when it is a dict of plain scalar/JSON values
    that touches no identity or provenance field, and (M-22) when the
    ``source_quote`` it carries is actually present in the source text.
    """
    if corrected in (None, {}, []):
        return None, ""
    if not isinstance(corrected, dict):
        return None, f"corrected payload is {type(corrected).__name__}, not an object"
    touched = sorted(_FORBIDDEN_CORRECTION_FIELDS.intersection(corrected))
    if touched:
        return None, f"corrected payload rewrites protected fields {touched}"
    if "source_quote" in corrected:
        if not source_quote_supported(corrected["source_quote"], section_data):
            return None, "corrected source_quote is not present in the source text"
    for key, value in corrected.items():
        if not isinstance(key, str) or not key.strip():
            return None, f"corrected payload has a non-string key {key!r}"
        if isinstance(value, (dict, list, set, tuple)):
            return None, f"corrected payload field {key!r} is a container, expected a scalar"
    return dict(corrected), ""


def _review_item(
    clinrec_id,
    item: dict,
    regimen: dict,
    extracted: dict,
    *,
    reason: str,
    confidence: float,
    issues: list,
    expected_fix: str,
) -> dict:
    """Build one review entry, ALWAYS carrying the extracted data intact.

    The old code substituted ``regimen = {}`` for a surplus regimen, so
    ``"extracted_data": {}`` -- the extracted record destroyed -- reached the
    physician review queue.
    """
    return {
        "clinrec_id": clinrec_id,
        "guideline_name": regimen.get("guideline_name") if regimen else None,
        "code_version": regimen.get("code_version") if regimen else None,
        "pdf_file": regimen.get("pdf_file") if regimen else None,
        "abx_level": item.get("abx_level"),
        "reason": reason,
        "confidence": confidence,
        "page_number": regimen.get("page_number", "") if regimen else "",
        "section_name": regimen.get("section_name", "") if regimen else "",
        "extracted_data": extracted,
        "expected_fix": expected_fix,
        "validation_issues": [str(i) for i in (issues or [])],
    }


async def cmd_knowledge(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE: Knowledge Base Generation[/]\n")

    if not EXTRACTION_VALIDATED_JSON.exists():
        console.print(f"[red]File not found: {EXTRACTION_VALIDATED_JSON}[/]")
        console.print("Run [bold]validate[/] first.")
        return

    regimens = orjson.loads(EXTRACTION_VALIDATED_JSON.read_bytes())
    console.print(f"  Validated regimens: {len(regimens)}")

    if not regimens:
        console.print("  [yellow]No validated regimens to save[/]")
        return

    from database import init_db
    db = init_db()
    init_regimens_table(db)

    save_regimens(db, regimens)
    console.print(f"  Saved {len(regimens)} regimens to metadata.sqlite")

    by_clinrec = {}
    for r in regimens:
        clinrec_id = r.get("clinrec_id")
        if clinrec_id not in by_clinrec:
            by_clinrec[clinrec_id] = {
                "clinrec_id": clinrec_id,
                "guideline_name": r.get("guideline_name"),
                "code_version": r.get("code_version"),
                "pdf_file": r.get("pdf_file"),
                "pdf_sha256": r.get("pdf_sha256"),
                "publication_date": r.get("publication_date"),
                "diagnosis": r.get("diagnosis"),
                "mkb": r.get("mkb"),
                "extraction_version": r.get("extraction_version"),
                "extraction_model": r.get("extraction_model"),
                "validation_model": r.get("validation_model"),
                "extracted_at": r.get("extracted_at"),
                "validated_at": r.get("validated_at"),
                "regimens": [],
            }
        regimen_fields = {k: v for k, v in r.items() if k not in ("clinrec_id", "clinrec_name", "pdf_sha256", "publication_date", "extraction_version", "extraction_model", "validation_model", "extracted_at", "validated_at", "_missing_source")}
        by_clinrec[clinrec_id]["regimens"].append(regimen_fields)

    knowledge_base = list(by_clinrec.values())
    KNOWLEDGE_BASE_JSON.write_bytes(orjson.dumps(knowledge_base, option=orjson.OPT_INDENT_2))
    console.print(f"  Saved to {KNOWLEDGE_BASE_JSON} ({len(knowledge_base)} guidelines)")

    db.close()


async def cmd_update(args: argparse.Namespace) -> None:
    console.print("[bold blue]STAGE 7: Update metadata + antibiotic_guidelines.json[/]\n")
    items = _load_items()

    save_metadata(items)
    console.print(f"  Saved to metadata.sqlite ({len(items)} records)")

    save_antibiotic_json(items)
    console.print("  Saved to antibiotic_guidelines.json")


async def cmd_verify(args: argparse.Namespace) -> None:
    console.print("[bold blue]Verification + Report[/]\n")
    items = _load_items()

    total = len(items)
    ok = sum(1 for i in items if i.get("pdf_path"))
    fail = total - ok
    abx = sum(1 for i in items if i.get("has_antibiotics"))
    no_abx = total - abx

    console.print(f"  Total:   {total}")
    console.print(f"  PDF OK:  {ok}")
    console.print(f"  Failed:  {fail}")
    console.print(f"  ABX:     {abx}")
    console.print(f"  No ABX:  {no_abx}")

    corrupted = 0
    for item in items:
        path_str = item.get("pdf_path", "")
        if not path_str:
            continue
        p = Path(path_str)
        if not p.exists():
            corrupted += 1
            continue
        if p.stat().st_size < 100:
            corrupted += 1
            continue
    if corrupted:
        console.print(f"  [yellow]Corrupted/missing: {corrupted}[/]")
    else:
        console.print(f"  [green]All PDFs present and non-empty[/]")

    report = generate_report(items)
    console.print("\n" + report)

    # L-4: the report was written to the CWD, so where it landed depended on
    # where the operator happened to be standing.  It now lands next to the
    # pipeline's own data directory, and the resolved path is printed.
    report_dir = EXTRACTION_RAW_JSON.parent
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.txt"
    report_path.write_text(report, encoding="utf-8")
    console.print(f"\n  Report saved to {report_path}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        description="Clinical Recommendations Downloader & Analyzer"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dl = sub.add_parser("download", help="Fetch list + download all PDFs")
    p_dl.add_argument("--page-size", type=int, default=200, help="Records per API page")

    sub.add_parser("analyze", help="Extract text + detect antibiotics")

    sub.add_parser("filter", help="Split PDFs into antibiotics / other")

    sub.add_parser("classify", help="A/B/C/D classification (rule-based)")

    sub.add_parser("gate", help="Antibiotic gate: filter process/review/skip")

    p_ext = sub.add_parser("extract_raw", help="LLM extraction -> extraction_raw.json (UNVALIDATED)")
    p_ext.add_argument("--force", action="store_true", help="Reprocess all")
    p_ext.add_argument("--limit", type=int, default=0, help="Max items to process (0 = all)")

    sub.add_parser("validate", help="GLM validation -> extraction_validated.json + review_required.json")

    sub.add_parser("knowledge", help="Generate knowledge_base.json + populate SQLite")

    sub.add_parser("update", help="Save metadata.sqlite + antibiotic_guidelines.json")

    sub.add_parser("verify", help="Verification + final report")

    args = parser.parse_args()

    cmds = {
        "download": cmd_download,
        "analyze": cmd_analyze,
        "filter": cmd_filter,
        "classify": cmd_classify,
        "gate": cmd_gate,
        "extract_raw": cmd_extract_raw,
        "validate": cmd_validate,
        "knowledge": cmd_knowledge,
        "update": cmd_update,
        "verify": cmd_verify,
    }

    asyncio.run(cmds[args.cmd](args))


if __name__ == "__main__":
    main()
