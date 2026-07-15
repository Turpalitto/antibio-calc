#!/usr/bin/env python3
"""prefilter.py — Rule-based PDF prefilter for ANTIBIO pipeline.

Удалить этот файл: move_archived_pdfs.py (очистка при необх.)

Usage:
  python -m src.pipeline.prefilter --dry-run
  python -m src.pipeline.prefilter --batch 50
  python -m src.pipeline.prefilter --all
  python -m src.pipeline.prefilter --audit
  python -m src.pipeline.prefilter --restore
"""

import argparse
import json
import logging
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson

from config import BASE_DIR, CLINRECS_JSON

logger = logging.getLogger(__name__)

# Paths
RULES_FILE = BASE_DIR / ".." / "prefilter_rules.json"
# Actually, prefilter_rules.json is in the ANTIBIO root. Let me resolve it properly.
# BASE_DIR = C:\clinrec_downloader, so C:\clinrec_downloader/../prefilter_rules.json = C:\prefilter_rules.json? No.
# The ANTIBIO root is C:\ANTIBIO. prefilter_rules.json lives there.
ANTIBIO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_FILE = ANTIBIO_ROOT / "prefilter_rules.json"
DRY_RUN_MANIFEST = BASE_DIR / "dry_run_manifest.json"
MOVEMENT_MANIFEST = BASE_DIR / "movement_manifest.json"
ACTIVE_DIR = BASE_DIR / "downloads_active"
ARCHIVE_NO_ABX = BASE_DIR / "archive_no_antibiotics"
ARCHIVE_REVIEW = BASE_DIR / "archive_review"


def load_rules() -> dict:
    if not RULES_FILE.exists():
        logger.error("prefilter_rules.json not found at %s", RULES_FILE)
        sys.exit(1)
    return orjson.loads(RULES_FILE.read_bytes())


def load_items() -> list[dict]:
    items = orjson.loads(CLINRECS_JSON.read_bytes())
    for item in items:
        pp = item.get("pdf_path", "")
        if pp and not Path(pp).is_absolute():
            item["pdf_path"] = str(Path(BASE_DIR) / pp)
    return items


def _get_mkb_codes(item: dict) -> list[str]:
    mkbs = item.get("Mkbs") or []
    codes = []
    for m in mkbs:
        code = (m.get("MkbCode") or "").strip()
        if code:
            codes.append(code)
    return codes


def _get_name(item: dict) -> str:
    return (item.get("Name") or "").lower()


def _default_decision(item: dict, rules: dict) -> tuple[str, str]:
    """Compute default decision from has_antibiotics + abx_level + abx_score."""
    has_abx = item.get("has_antibiotics", False)
    abx_level = (item.get("abx_level") or "D").upper()
    abx_score = item.get("abx_score")
    if abx_score is None:
        abx_score = 0

    defaults = rules.get("defaults", {})
    if has_abx and abx_level in ("A", "B"):
        return defaults.get("has_antibiotics_True_abx_level_AB", "need_llm"), "default"
    if has_abx and abx_level in ("C", "D"):
        return defaults.get("has_antibiotics_True_abx_level_CD", "need_llm"), "default"
    if not has_abx and abx_score is not None and abx_score >= 10:
        return defaults.get("has_antibiotics_False_abx_score_gte_10", "review"), "default"
    if not has_abx and abx_score is not None and abx_score < 10:
        return defaults.get("has_antibiotics_False_abx_score_lt_10", "no_antibiotics"), "default"
    return defaults.get("has_antibiotics_False_abx_score_null", "no_antibiotics"), "default"


def _match_keywords(name: str, keywords: list[str]) -> list[str]:
    """Return matched keywords from name (lowercase)."""
    matched = []
    for kw in keywords:
        if kw.lower() in name:
            matched.append(kw)
    return matched


def _match_mkb_prefix(mkb_codes: list[str], prefixes: list[str]) -> list[str]:
    """Return matched MKB prefixes."""
    matched = []
    for code in mkb_codes:
        for prefix in prefixes:
            if code.startswith(prefix):
                matched.append(f"{prefix} ({code})")
                break
    return matched


def _check_conditions(conditions: dict, item: dict) -> bool:
    """Check if conditions are met. Returns True if item satisfies all conditions."""
    has_abx = item.get("has_antibiotics", False)
    abx_score = item.get("abx_score") or 0
    abx_level = (item.get("abx_level") or "D").upper()

    if "has_antibiotics" in conditions:
        if conditions["has_antibiotics"] != has_abx:
            return False
    if "has_antibiotics_not" in conditions:
        if conditions["has_antibiotics_not"] == has_abx:
            return False
    if "abx_score_lt" in conditions:
        if abx_score >= conditions["abx_score_lt"]:
            return False
    if "abx_score_gt" in conditions:
        if abx_score <= conditions["abx_score_gt"]:
            return False
    if "abx_level_in" in conditions:
        if abx_level not in conditions["abx_level_in"]:
            return False
    return True


def _check_rule(rule: dict, item: dict) -> dict | None:
    """Check a single rule against an item. Returns match info or None."""
    name = _get_name(item)
    mkb_codes = _get_mkb_codes(item)
    matched_kw = []
    matched_mkb = []
    match_info = {"matched": False, "matched_keyword": None, "matched_mkb": None}

    # Check conditions (for upgrade_to_active and downgrade_to_review)
    if "conditions" in rule:
        if not _check_conditions(rule["conditions"], item):
            return None

    # Check require (for force_exclude — all must be true)
    if "require" in rule:
        if not _check_conditions(rule["require"], item):
            return None

    match_any = rule.get("match_any", {})
    match_all = rule.get("match_all", {})

    # match_any: at least one must match
    if match_any:
        kw_list = match_any.get("name_keywords", [])
        mkb_list = match_any.get("mkb_codes_prefix", [])

        if kw_list:
            matched_kw = _match_keywords(name, kw_list)
        if mkb_list:
            matched_mkb = _match_mkb_prefix(mkb_codes, mkb_list)

        if not matched_kw and not matched_mkb:
            return None

        match_info["matched_keyword"] = matched_kw[:3] if matched_kw else None
        match_info["matched_mkb"] = matched_mkb[:3] if matched_mkb else None

    # match_all: all must match (simplified — just check name keywords)
    if match_all:
        kw_list = match_all.get("name_keywords", [])
        mkb_list = match_all.get("mkb_codes_prefix", [])

        for kw in kw_list:
            if kw.lower() not in name:
                return None

        if mkb_list:
            all_mkb_match = all(
                any(mkb_code.startswith(prefix) for mkb_code in mkb_codes)
                for prefix in mkb_list
            )
            if not all_mkb_match:
                return None

            match_info["matched_mkb"] = mkb_list[:3]

        if kw_list:
            match_info["matched_keyword"] = kw_list[:3]

    match_info["matched"] = True
    return match_info


def classify_item(item: dict, rules: dict) -> dict:
    """Classify a single item. Returns full decision record."""
    default_decision, default_reason = _default_decision(item, rules)
    final_decision = default_decision
    matched_rule = None
    matched_detail = None
    override = False
    priority = 0

    # Sort rules by priority (highest first)
    rule_list = []
    for rule_name, rule_body in rules.get("rules", {}).items():
        rule_list.append((rule_name, rule_body))
    rule_list.sort(key=lambda x: x[1].get("priority", 0), reverse=True)

    force_override = False  # True after a force_ rule changed the decision
    for rule_name, rule_body in rule_list:
        # If a higher-priority force rule already overrode, skip lower-priority force rules
        if force_override and rule_name.startswith("force_"):
            continue

        match_info = _check_rule(rule_body, item)
        if match_info and match_info["matched"]:
            # Determine what decision this rule wants
            if rule_name == "force_include":
                new_decision = "need_llm"
            elif rule_name == "force_exclude":
                new_decision = "no_antibiotics"
            elif rule_name == "force_review":
                new_decision = "review"
            elif rule_name == "upgrade_to_active":
                if default_decision != "need_llm":
                    new_decision = "need_llm"
                else:
                    new_decision = None  # Already need_llm
            elif rule_name == "downgrade_to_review":
                if default_decision == "need_llm":
                    new_decision = "review"
                else:
                    new_decision = None  # Already not need_llm
            else:
                new_decision = None

            if new_decision:
                if new_decision != default_decision:
                    final_decision = new_decision
                    override = True
                if rule_name.startswith("force_"):
                    force_override = True  # Lock: no lower-priority rule can override

            # Track highest-priority matched rule (even if it confirms default)
            if matched_rule is None or rule_body.get("priority", 0) >= priority:
                matched_rule = rule_name
                priority = rule_body.get("priority", 0)
                matched_detail = match_info

    # Ensure no_antibiotics only if absolutely sure
    if final_decision == "no_antibiotics" and not override:
        # Only default no_antibiotics without override is allowed
        pass

    return {
        "Id": item.get("Id"),
        "Name": item.get("Name"),
        "pdf_path": item.get("pdf_path"),
        "diagnosis": item.get("Name"),
        "mkb_codes": _get_mkb_codes(item),
        "has_antibiotics": item.get("has_antibiotics", False),
        "abx_level": item.get("abx_level", "D"),
        "abx_score": item.get("abx_score", 0),
        "default_decision": default_decision,
        "final_decision": final_decision,
        "matched_rule": matched_rule,
        "matched_keyword": (matched_detail or {}).get("matched_keyword"),
        "matched_mkb": (matched_detail or {}).get("matched_mkb"),
        "override": override,
        "priority": priority,
        "reason": f"default={default_decision}, matched={matched_rule or '-none-'}, override={override}",
    }


def create_directories():
    for d in [ACTIVE_DIR, ARCHIVE_NO_ABX, ARCHIVE_REVIEW]:
        d.mkdir(parents=True, exist_ok=True)


def move_pdf(decision: dict, target_dir: Path, manifest: list):
    pp = decision.get("pdf_path")
    if not pp:
        return False
    src = Path(pp)
    if not src.exists():
        logger.warning("PDF not found: %s", src)
        return False
    filename = src.name
    dest = target_dir / filename
    # Handle name collisions
    if dest.exists():
        stem = src.stem
        suffix = src.suffix
        dest = target_dir / f"{stem}_{decision['Id']}{suffix}"

    shutil.move(str(src), str(dest))
    manifest.append({
        "source_path": str(src),
        "destination_path": str(dest),
        "Id": decision["Id"],
        "Name": decision["Name"],
        "final_decision": decision["final_decision"],
        "default_decision": decision["default_decision"],
        "matched_rule": decision["matched_rule"],
        "override": decision["override"],
        "reason": decision["reason"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return True


def run_dry_run(items: list[dict], rules: dict) -> list[dict]:
    results = []
    for item in items:
        result = classify_item(item, rules)
        results.append(result)
    return results


def print_stats(results: list[dict], elapsed: float):
    total = len(results)
    active = sum(1 for r in results if r["final_decision"] == "need_llm")
    no_abx = sum(1 for r in results if r["final_decision"] == "no_antibiotics")
    review = sum(1 for r in results if r["final_decision"] == "review")
    overrides = sum(1 for r in results if r["override"])
    ab_A = sum(1 for r in results if r.get("abx_level") == "A")
    ab_B = sum(1 for r in results if r.get("abx_level") == "B")
    ab_C = sum(1 for r in results if r.get("abx_level") == "C")
    ab_D = sum(1 for r in results if r.get("abx_level") == "D")

    # Rule statistics
    from collections import Counter
    rule_counter = Counter(r["matched_rule"] for r in results if r["matched_rule"])
    all_rules = ["force_include", "force_exclude", "force_review", "upgrade_to_active", "downgrade_to_review"]

    print(f"\n{'='*60}")
    print(f"  PREFILTER DRY RUN — STATISTICS")
    print(f"{'='*60}")
    print(f"  Total PDFs analyzed:     {total}")
    print(f"  Time:                    {elapsed:.2f}s")
    print()
    print(f"  {'downloads_active/':<35} {active:>5}  ({active/total*100:.1f}%)")
    print(f"  {'archive_no_antibiotics/':<35} {no_abx:>5}  ({no_abx/total*100:.1f}%)")
    print(f"  {'archive_review/':<35} {review:>5}  ({review/total*100:.1f}%)")
    print()
    print(f"  {'Decisions overridden by rules:':<35} {overrides:>5}  ({overrides/total*100:.1f}%)")
    print()
    print(f"  {'A-level (known ABX):':<35} {ab_A:>5}")
    print(f"  {'B-level (likely ABX):':<35} {ab_B:>5}")
    print(f"  {'C-level (possible ABX):':<35} {ab_C:>5}")
    print(f"  {'D-level (unlikely ABX):':<35} {ab_D:>5}")
    print()

    print(f"  {'Rule usage statistics:':<35}")
    for rule_name in all_rules:
        count = rule_counter.get(rule_name, 0)
        pct = count / total * 100 if total > 0 else 0
        unused = " [UNUSED]" if count == 0 else ""
        print(f"    {rule_name:<32} {count:>5} ({pct:>5.1f}%){unused}")
    print()

    # Savings estimate
    llm_savings = no_abx + review
    time_per_pdf = 60  # seconds (average LLM call time)
    saved_time = llm_savings * time_per_pdf
    print(f"  {'Estimated LLM call savings:':<35} {llm_savings:>5}  (-{llm_savings/total*100:.1f}%)")
    print(f"  {'Estimated time saved:':<35} {saved_time:.0f}s  ({saved_time/60:.1f}min / {saved_time/3600:.2f}h)")
    print(f"{'='*60}\n")


def _safe(text: Any, maxlen: int = 80) -> str:
    """Convert to string, replace unencodable chars."""
    s = str(text) if text is not None else "?"
    return s.encode("cp1251", errors="replace").decode("cp1251")[:maxlen]


def audit_no_antibiotics(results: list[dict], sample_size: int = 100):
    """Audit random sample of items destined for archive_no_antibiotics."""
    no_abx_items = [r for r in results if r["final_decision"] == "no_antibiotics"]

    if not no_abx_items:
        print("  No items destined for archive_no_antibiotics. Nothing to audit.")
        return True

    sample = random.sample(no_abx_items, min(sample_size, len(no_abx_items)))

    print(f"\n{'='*60}")
    print(f"  AUDIT: {len(sample)} random items from archive_no_antibiotics")
    print(f"{'='*60}")

    suspicious = 0
    for s in sample:
        name = _safe(s.get("Name"), 80)
        mkb = _safe("; ".join(s.get("mkb_codes", [])), 60)
        rule = s.get("matched_rule") or "default"
        reason = _safe(s.get("reason", ""), 80)
        print(f"  [{s['Id']}] {name}")
        print(f"       MKB={mkb}  rule={rule}  score={s.get('abx_score')}  level={s.get('abx_level')}")
        print(f"       reason={reason}")
        print()

        # Check for potentially infectious items
        suspicious_keywords = ["инфекци", "гнойн", "сепсис", "бактери", "антибиотик"]
        name_lower = (s.get("Name") or "").lower()
        if any(kw in name_lower for kw in suspicious_keywords):
            suspicious += 1
            print(f"       *** SUSPICIOUS: name contains infection-related keyword! ***")

    print(f"  Total audited: {len(sample)}")
    print(f"  Suspicious: {suspicious}")

    if suspicious > 0:
        print(f"\n  *** Found {suspicious} potentially infectious items in archive_no_antibiotics.")
        print(f"  Recommend: update prefilter_rules.json before proceeding.")
        return False

    print(f"  [OK] No suspicious items found. Safe to proceed.")
    return True


def cmd_dry_run():
    rules = load_rules()
    items = load_items()

    print(f"\n  Loading {len(items)} items from clinrecs.json")
    print(f"  Applying rules from {RULES_FILE}")

    t0 = time.monotonic()
    results = run_dry_run(items, rules)
    elapsed = time.monotonic() - t0

    # Save manifest
    DRY_RUN_MANIFEST.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    print(f"  Dry run manifest saved: {DRY_RUN_MANIFEST}")

    print_stats(results, elapsed)

    # Ask for audit
    print("  Next step: python -m src.pipeline.prefilter --audit")


def _is_suspicious(item: dict) -> bool:
    """Check if an item may contain antibiotic content despite default no_antibiotics."""
    suspicious_keywords = [
        "инфекци", "гнойн", "сепсис", "бактери", "антибиотик",
        "антимикробн", "противомикробн", "антибактериальн",
        "пневмони", "менингит", "эндокардит", "перитонит",
        "остеомиелит", "пиелонефрит", "абсцесс", "флегмон",
        "ранев", "трофическ",
        "послеоперацион", "хирургическ",
        "ожог", "пролежн",
    ]
    name_lower = (item.get("Name") or "").lower()
    matched = [kw for kw in suspicious_keywords if kw in name_lower]
    return matched


def cmd_full_audit():
    """Full scan of all archive_no_antibiotics items. Auto-move suspicious to review."""
    if not DRY_RUN_MANIFEST.exists():
        print("  Dry run manifest not found. Run --dry-run first.")
        return
    results = orjson.loads(DRY_RUN_MANIFEST.read_bytes())
    no_abx_items = [r for r in results if r["final_decision"] == "no_antibiotics"]

    print(f"\n  Full audit: scanning all {len(no_abx_items)} no_antibiotics items...")

    suspicious = []
    for r in no_abx_items:
        matched = _is_suspicious(r)
        if matched:
            suspicious.append(r)
            print(f"  *** SUSPICIOUS [{r['Id']}] {_safe(r.get('Name'), 70)}")
            print(f"      keywords={matched}  score={r.get('abx_score')}  level={r.get('abx_level')}")

    if not suspicious:
        print(f"\n  [OK] All {len(no_abx_items)} items in archive_no_antibiotics appear safe.")
        return True

    print(f"\n  Found {len(suspicious)} potentially infectious items in archive_no_antibiotics.")
    print(f"  These will be moved to archive_review/ for manual inspection.")

    # Update final_decision to review
    ids_to_move = {r["Id"] for r in suspicious}
    updated = 0
    for r in results:
        if r["Id"] in ids_to_move:
            r["final_decision"] = "review"
            r["matched_rule"] = "full_audit"
            r["override"] = True
            r["reason"] = f"auto-moved from no_antibiotics by full_audit (keywords: {','.join(_is_suspicious(r))})"
            updated += 1

    # Re-save manifest
    DRY_RUN_MANIFEST.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    print(f"\n  Updated dry_run_manifest.json: {updated} items moved to review.")

    print(f"\n  Action required: review these items manually after mass move")
    print(f"  After review, you can: python -m src.pipeline.prefilter --restore")
    return True


def cmd_audit():
    if not DRY_RUN_MANIFEST.exists():
        print("  Dry run manifest not found. Run --dry-run first.")
        return
    results = orjson.loads(DRY_RUN_MANIFEST.read_bytes())
    audit_no_antibiotics(results)


def cmd_move_batch(batch_size: int = 50):
    if not DRY_RUN_MANIFEST.exists():
        print("  Dry run manifest not found. Run --dry-run first.")
        return

    results = orjson.loads(DRY_RUN_MANIFEST.read_bytes())
    create_directories()

    # Separate by decision
    active = [r for r in results if r["final_decision"] == "need_llm"]
    no_abx = [r for r in results if r["final_decision"] == "no_antibiotics"]
    review = [r for r in results if r["final_decision"] == "review"]

    # Move starting with no_abx and review first (clean up non-essential)
    manifest = []

    def _do_move(items_list: list[dict], target_dir: Path, label: str, limit: int):
        moved = 0
        for r in items_list:
            if moved >= limit:
                break
            if move_pdf(r, target_dir, manifest):
                moved += 1
        if moved:
            print(f"  Moved {moved} PDFs to {label}")
        return moved

    remaining = batch_size
    remaining -= _do_move(no_abx, ARCHIVE_NO_ABX, "archive_no_antibiotics", remaining)
    remaining -= _do_move(review, ARCHIVE_REVIEW, "archive_review", remaining)
    remaining -= _do_move(active, ACTIVE_DIR, "downloads_active", remaining)

    MOVEMENT_MANIFEST.write_bytes(orjson.dumps(manifest, option=orjson.OPT_INDENT_2))
    print(f"\n  Movement manifest saved: {MOVEMENT_MANIFEST}")
    print(f"  Total moved this batch: {len(manifest)}")

    return len(manifest)


def cmd_move_all():
    if not DRY_RUN_MANIFEST.exists():
        print("  Dry run manifest not found. Run --dry-run first.")
        return

    results = orjson.loads(DRY_RUN_MANIFEST.read_bytes())
    create_directories()

    manifest = []

    # Move archive_no_antibiotics first
    no_abx = [r for r in results if r["final_decision"] == "no_antibiotics"]
    for r in no_abx:
        move_pdf(r, ARCHIVE_NO_ABX, manifest)
    print(f"  Moved {len(no_abx)} PDFs to archive_no_antibiotics/")

    # Move archive_review
    review = [r for r in results if r["final_decision"] == "review"]
    for r in review:
        move_pdf(r, ARCHIVE_REVIEW, manifest)
    print(f"  Moved {len(review)} PDFs to archive_review/")

    # Move active last
    active = [r for r in results if r["final_decision"] == "need_llm"]
    for r in active:
        move_pdf(r, ACTIVE_DIR, manifest)
    print(f"  Moved {len(active)} PDFs to downloads_active/")

    MOVEMENT_MANIFEST.write_bytes(orjson.dumps(manifest, option=orjson.OPT_INDENT_2))
    print(f"\n  Movement manifest saved: {MOVEMENT_MANIFEST}")
    print(f"  Total moved: {len(manifest)}")

    if len(manifest) != len(results):
        print(f"  Warning: {len(results) - len(manifest)} items had missing PDFs")

    return len(manifest)


def cmd_restore():
    """Restore all PDFs from movement_manifest.json back to original locations."""
    if not MOVEMENT_MANIFEST.exists():
        print("  Movement manifest not found:", MOVEMENT_MANIFEST)
        return

    manifest = orjson.loads(MOVEMENT_MANIFEST.read_bytes())
    restored = 0
    errors = 0

    for entry in manifest:
        src = Path(entry["destination_path"])
        dst = Path(entry["source_path"])

        if not src.exists():
            logger.warning("  Not found: %s", src)
            errors += 1
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        restored += 1

    print(f"  Restored: {restored} PDFs")
    print(f"  Errors:   {errors}")

    # Clean up empty directories
    for d in [ACTIVE_DIR, ARCHIVE_NO_ABX, ARCHIVE_REVIEW]:
        if d.exists():
            remaining = list(d.iterdir())
            if not remaining:
                d.rmdir()
                print(f"  Removed empty directory: {d}")


def main():
    parser = argparse.ArgumentParser(description="ANTIBIO PDF Prefilter")
    parser.add_argument("--dry-run", action="store_true", help="Run analysis without moving files")
    parser.add_argument("--audit", action="store_true", help="Audit random sample of archive_no_antibiotics")
    parser.add_argument("--full-audit", action="store_true", help="Full scan all no_antibiotics items, auto-move suspicious to review")
    parser.add_argument("--batch", type=int, default=0, help="Move N PDFs as test batch")
    parser.add_argument("--all", action="store_true", help="Move all PDFs")
    parser.add_argument("--restore", action="store_true", help="Restore all PDFs from manifest")
    args = parser.parse_args()

    if args.dry_run:
        cmd_dry_run()
    elif args.full_audit:
        cmd_full_audit()
    elif args.audit:
        cmd_audit()
    elif args.batch > 0:
        cmd_move_batch(args.batch)
    elif args.all:
        cmd_move_all()
    elif args.restore:
        cmd_restore()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
