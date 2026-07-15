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

import httpx
import orjson
from rich.console import Console
from rich.logging import RichHandler


_write_lock = asyncio.Lock()


async def _safe_write(path: Path, data: list) -> None:
    """Thread-safe JSON write with integrity check. No atomic rename (too fragile on Windows)."""
    async with _write_lock:
        blob = orjson.dumps(data, option=orjson.OPT_INDENT_2)
        path.write_bytes(blob)
        # Verify immediately
        back = orjson.loads(path.read_bytes())
        if not isinstance(back, list):
            raise RuntimeError("Write corruption: not a list")
        if len(back) < len(data):
            raise RuntimeError(f"Write corruption: expected >= {len(data)}, got {len(back)}")



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
    load_validated_regimens,
    save_antibiotic_json,
    save_metadata,
    save_regimens,
    split_by_category,
)
from downloader import download_all_pdfs
from extractor_llm import extract_regimens, check_source_fields, validate_regimens
from progress import (
    get_pending_items,
    load_progress,
    mark_extraction_done,
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


def _resolve_pdf_path(item: dict) -> str | None:
    pp = item.get("pdf_path", "")
    if not pp:
        return None
    p = Path(pp)
    if p.is_absolute():
        return pp
    resolved = Path(BASE_DIR) / pp
    return str(resolved) if resolved.exists() else pp


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
    t0 = time.monotonic()
    processed_count = 0
    regimen_count = 0
    checkpoint_counter = 0
    checkpoint_t0 = time.monotonic()

    async def _save_incremental(regimens: list[dict]) -> None:
        """Thread-safe incremental save with integrity check + fsync."""
        async with save_lock:
            existing = []
            if EXTRACTION_RAW_JSON.exists():
                try:
                    existing = orjson.loads(EXTRACTION_RAW_JSON.read_bytes())
                    if not isinstance(existing, list):
                        existing = []
                except Exception:
                    logger.error("Corrupted extraction_raw.json — recovery needed")
                    raise
            existing.extend(regimens)
            await _safe_write(EXTRACTION_RAW_JSON, existing)
            # Additional fsync for crash safety
            try:
                fd = os.open(str(EXTRACTION_RAW_JSON), os.O_RDONLY)
                os.fsync(fd)
                os.close(fd)
            except OSError:
                pass

    async def process_one(item: dict) -> None:
        nonlocal failed, processed_count, regimen_count, checkpoint_counter
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
                mark_extraction_done(clinrec_id, pdf_sha256, 0)
                processed_count += 1
                console.print(f"  [{clinrec_id}] no relevant text — skipped")
                return

            try:
                regimens = await extract_regimens(item, section_data)
                if not regimens:
                    mark_extraction_done(clinrec_id, pdf_sha256, 0)
                    processed_count += 1
                    console.print(f"  [{clinrec_id}] {item.get('Name', '')[:40]}: 0 regimens")
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

    elapsed = time.monotonic() - t0
    console.print(f"\n  Processed {processed_count} PDFs, extracted {regimen_count} regimens in {elapsed:.1f}s")
    if checkpoint_counter >= 10:
        console.print(f"  Final checkpoint: {checkpoint_counter} checkpoints written")
    if failed:
        console.print(f"  [red]Failed: {len(failed)}[/]")
    console.print(f"  Saved to {EXTRACTION_RAW_JSON} (incremental, UNVALIDATED)")
    console.print(f"  Progress: {EXTRACTION_RAW_JSON.with_name('extraction_progress.json')} (fsync after every PDF)")


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
                review_items.append({
                    "clinrec_id": clinrec_id,
                    "guideline_name": r.get("guideline_name"),
                    "code_version": r.get("code_version"),
                    "pdf_file": r.get("pdf_file"),
                    "abx_level": item.get("abx_level"),
                    "reason": "validation_api_error",
                    "confidence": 0.0,
                    "page_number": r.get("page_number", ""),
                    "section_name": r.get("section_name", ""),
                    "extracted_data": r,
                    "expected_fix": f"Validation API error: {exc}",
                    "validation_issues": [str(exc)],
                })
            continue

        for idx, result in enumerate(results):
            regimen = regimens[idx] if idx < len(regimens) else {}
            confidence = result.get("confidence", 0.0)
            valid = result.get("valid", False)
            issues = result.get("issues", [])
            corrected = result.get("corrected")

            if corrected and valid:
                regimen = {**regimen, **corrected}

            if regimen.get("_missing_source"):
                review_items.append({
                    "clinrec_id": clinrec_id,
                    "guideline_name": regimen.get("guideline_name"),
                    "code_version": regimen.get("code_version"),
                    "pdf_file": regimen.get("pdf_file"),
                    "abx_level": item.get("abx_level"),
                    "reason": "missing_source_evidence",
                    "confidence": confidence,
                    "page_number": regimen.get("page_number", ""),
                    "section_name": regimen.get("section_name", ""),
                    "extracted_data": regimen,
                    "expected_fix": "Add missing source fields (guideline_name, code_version, pdf_file, page_number, section_name, source_quote)",
                    "validation_issues": issues,
                })
            elif valid and confidence >= 0.9:
                regimen["validation_confidence"] = confidence
                regimen["validation_issues"] = issues
                regimen["validated"] = 1
                regimen["validation_model"] = VALIDATION_MODEL
                regimen["validated_at"] = datetime.now(timezone.utc).isoformat()
                validated.append(regimen)
            else:
                review_items.append({
                    "clinrec_id": clinrec_id,
                    "guideline_name": regimen.get("guideline_name"),
                    "code_version": regimen.get("code_version"),
                    "pdf_file": regimen.get("pdf_file"),
                    "abx_level": item.get("abx_level"),
                    "reason": "validation_failed",
                    "confidence": confidence,
                    "page_number": regimen.get("page_number", ""),
                    "section_name": regimen.get("section_name", ""),
                    "extracted_data": regimen,
                    "expected_fix": "; ".join(issues) if issues else "Confidence below 0.9",
                    "validation_issues": issues,
                })

        mark_validation_done(clinrec_id, min((r.get("confidence", 0) for r in results), default=0.0))

    elapsed = time.monotonic() - t0
    console.print(f"\n  Validated: {len(validated)} regimens")
    console.print(f"  Review required: {len(review_items)} regimens")
    console.print(f"  Time: {elapsed:.1f}s")

    from config import EXTRACTION_VALIDATED_JSON
    EXTRACTION_VALIDATED_JSON.write_bytes(orjson.dumps(validated, option=orjson.OPT_INDENT_2))
    console.print(f"  Saved to {EXTRACTION_VALIDATED_JSON}")

    existing_review = []
    if REVIEW_REQUIRED_JSON.exists():
        existing_review = orjson.loads(REVIEW_REQUIRED_JSON.read_bytes())
    from database import save_review_required
    save_review_required(existing_review + review_items, REVIEW_REQUIRED_JSON)
    console.print(f"  Updated {REVIEW_REQUIRED_JSON} ({len(existing_review) + len(review_items)} total)")


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

    # validate a few random PDFs
    import hashlib

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

    report_path = Path("report.txt")
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
