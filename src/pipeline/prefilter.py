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
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson

from config import BASE_DIR, CLINRECS_JSON
from downloader import unique_destination

logger = logging.getLogger(__name__)

# Paths.  prefilter_rules.json lives at the repository root, which is two levels
# above this module (src/pipeline/prefilter.py).  L-18: RULES_FILE was assigned
# TWICE, the first from BASE_DIR (which resolves to the data directory, not the
# repo root) under a comment that openly admitted it was wrong.
ANTIBIO_ROOT = Path(__file__).resolve().parents[2]
RULES_FILE = ANTIBIO_ROOT / "prefilter_rules.json"
DRY_RUN_MANIFEST = BASE_DIR / "dry_run_manifest.json"
MOVEMENT_MANIFEST = BASE_DIR / "movement_manifest.json"
ACTIVE_DIR = BASE_DIR / "downloads_active"
ARCHIVE_NO_ABX = BASE_DIR / "archive_no_antibiotics"
ARCHIVE_REVIEW = BASE_DIR / "archive_review"


def load_rules() -> dict:
    """Load the business rules.

    L-19: this called ``sys.exit(1)``, so importing module-level code or calling
    the function from a test or another tool killed the whole process instead of
    reporting a missing file.  It now raises, and ``main`` turns that into an
    exit code.
    """
    if not RULES_FILE.exists():
        raise FileNotFoundError(f"prefilter_rules.json not found at {RULES_FILE}")
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


def _as_bool(value: Any) -> bool:
    """Coerce a JSON boolean that may have been written as a string."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y", "да")
    return False


def _get_name(item: dict) -> str:
    return (item.get("Name") or "").lower()


def _default_decision(item: dict, rules: dict) -> tuple[str, str]:
    """Compute default decision from has_antibiotics + abx_level + abx_score."""
    has_abx = item.get("has_antibiotics", False)
    abx_level = (item.get("abx_level") or "D").upper()
    # M-32: `abx_score` was coerced None->0 immediately below, so the
    # `abx_score_null` rule could never fire and a rule intended to route a
    # score-less item to review silently sent it to no_antibiotics.  The None
    # case is now decided BEFORE any coercion.
    raw_score = item.get("abx_score")
    abx_score = 0 if raw_score is None else raw_score

    defaults = rules.get("defaults", {})
    if has_abx and abx_level in ("A", "B"):
        return defaults.get("has_antibiotics_True_abx_level_AB", "need_llm"), "default"
    if has_abx and abx_level in ("C", "D"):
        return defaults.get("has_antibiotics_True_abx_level_CD", "need_llm"), "default"
    if not has_abx and raw_score is None:
        return defaults.get("has_antibiotics_False_abx_score_null", "review"), "default"
    if abx_score >= 10:
        return defaults.get("has_antibiotics_False_abx_score_gte_10", "review"), "default"
    return defaults.get("has_antibiotics_False_abx_score_lt_10", "no_antibiotics"), "default"


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
    # M-42: `has_antibiotics` was compared as a strict bool, so a JSON rule with
    # the string "false" never matched anything and the rule was silently inert.
    has_abx = _as_bool(item.get("has_antibiotics", False))
    abx_score = item.get("abx_score") or 0
    abx_level = (item.get("abx_level") or "D").upper()

    if "has_antibiotics" in conditions:
        if _as_bool(conditions["has_antibiotics"]) != has_abx:
            return False
    if "has_antibiotics_not" in conditions:
        if _as_bool(conditions["has_antibiotics_not"]) == has_abx:
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

    # M-33: a rule carrying neither match_any nor match_all (e.g. a typo that
    # dropped `match_any`) returned matched=True, turning it into a BLANKET
    # OVERRIDE for the whole corpus.  A rule must state at least one criterion.
    if not match_any and not match_all:
        logger.error(
            "rule %r has no match criteria (no match_any, no match_all) -- "
            "ignoring it instead of matching every item", rule.get("name", "<unnamed>"),
        )
        return None

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
    # M-34: the deciding rule (the one that actually changed the outcome), tracked
    # separately from the highest-priority match.  With the `>=` comparison the old
    # code let a LATER rule of equal priority overwrite the report, so `matched_rule`
    # named the last rule seen rather than the one that decided.
    deciding_rule = None
    deciding_priority = 0
    deciding_detail = None

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
                    # The lock is intentional and load-bearing: a matching force_
                    # rule is the operator's explicit decision, and a lower-priority
                    # force_ rule must not be able to overturn it -- even when the
                    # higher-priority one merely confirmed the default
                    # (see test_force_include_confirms_default).
                    force_override = True

            if new_decision and new_decision != default_decision:
                deciding_rule = rule_name
                deciding_priority = rule_body.get("priority", 0)
                deciding_detail = match_info
                if matched_rule is None:
                    matched_rule = rule_name
                    priority = deciding_priority
                    matched_detail = match_info
            elif matched_rule is None:
                matched_rule = rule_name
                priority = rule_body.get("priority", 0)
                matched_detail = match_info

    # The DECIDING rule is what an operator needs to audit a decision; fall back to
    # the highest-priority match when the default stood (no rule overrode it).
    if deciding_rule is not None:
        matched_rule = deciding_rule
        priority = deciding_priority
        matched_detail = deciding_detail

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


def _append_movement_manifest(entries: list) -> None:
    """Merge new movements into the manifest INSTEAD of overwriting it.

    M-37: ``MOVEMENT_MANIFEST.write_bytes(...)`` replaced the file on every batch,
    so a second partial run destroyed the record of the first -- and `--restore`
    could then only put back the last batch, leaving earlier PDFs stranded in the
    archive directories.  Entries are keyed by (source, destination) so a re-run
    that moves the same file twice is idempotent.
    """
    if not entries:
        return
    existing: list[dict] = []
    if MOVEMENT_MANIFEST.exists():
        try:
            loaded = orjson.loads(MOVEMENT_MANIFEST.read_bytes())
            if isinstance(loaded, list):
                existing = loaded
        except Exception:
            logger.error("movement_manifest.json is unreadable; starting a fresh one")
    merged: dict[tuple[str, str], dict] = {
        (e.get("source_path", ""), e.get("destination_path", "")): e for e in existing
    }
    for entry in entries:
        merged[(entry.get("source_path", ""), entry.get("destination_path", ""))] = entry
    MOVEMENT_MANIFEST.write_bytes(
        orjson.dumps(list(merged.values()), option=orjson.OPT_INDENT_2)
    )


def create_directories():
    for d in [ACTIVE_DIR, ARCHIVE_NO_ABX, ARCHIVE_REVIEW]:
        d.mkdir(parents=True, exist_ok=True)


def move_pdf(decision: dict, target_dir: Path, manifest: list):
    """Move one PDF into ``target_dir`` and record it in ``manifest``.

    H-24 / M-37: the destination was built from the guideline NAME alone, so two
    distinct guidelines whose names sanitize to the same string collided and the
    second was either skipped or INHERITED the first document's path -- and
    therefore its pdf_sha256, anchoring every downstream artifact to the wrong
    PDF.  ``unique_destination`` disambiguates with the rubricator Id, which also
    makes re-running the move idempotent instead of appending ``_2`` forever.
    """
    pp = decision.get("pdf_path")
    if not pp:
        return False
    src = Path(pp)
    if not src.exists():
        logger.warning("PDF not found: %s", src)
        return False
    # H-24: `decision['Id']` raised TypeError/KeyError on a None or missing Id,
    # and a NULL primary key is worse than a collision.
    doc_id = decision.get("Id")
    if doc_id in (None, ""):
        raise ValueError(f"cannot move {src}: decision carries no rubricator Id")
    dest = unique_destination(target_dir, src.name, doc_id, source=src)

    shutil.move(str(src), str(dest))
    manifest.append({
        "source_path": str(src),
        "destination_path": str(dest),
        "Id": decision.get("Id"),
        "Name": decision.get("Name"),
        "final_decision": decision.get("final_decision"),
        "default_decision": decision.get("default_decision"),
        "matched_rule": decision.get("matched_rule"),
        "override": decision.get("override", False),
        "reason": decision.get("reason", ""),
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

    # M-35: every percentage below divided by `total`, which is ZeroDivisionError
    # on an empty corpus -- so `--dry-run` on an empty manifest crashed instead of
    # reporting "0 PDFs".
    def pct(n: int) -> float:
        return (n / total * 100) if total else 0.0

    print(f"\n{'='*60}")
    print(f"  PREFILTER DRY RUN — STATISTICS")
    print(f"{'='*60}")
    print(f"  Total PDFs analyzed:     {total}")
    print(f"  Time:                    {elapsed:.2f}s")
    print()
    print(f"  {'downloads_active/':<35} {active:>5}  ({pct(active):.1f}%)")
    print(f"  {'archive_no_antibiotics/':<35} {no_abx:>5}  ({pct(no_abx):.1f}%)")
    print(f"  {'archive_review/':<35} {review:>5}  ({pct(review):.1f}%)")
    print()
    print(f"  {'Decisions overridden by rules:':<35} {overrides:>5}  ({pct(overrides):.1f}%)")
    print()
    print(f"  {'A-level (known ABX):':<35} {ab_A:>5}")
    print(f"  {'B-level (likely ABX):':<35} {ab_B:>5}")
    print(f"  {'C-level (possible ABX):':<35} {ab_C:>5}")
    print(f"  {'D-level (unlikely ABX):':<35} {ab_D:>5}")
    print()

    print(f"  {'Rule usage statistics:':<35}")
    for rule_name in all_rules:
        count = rule_counter.get(rule_name, 0)
        share = pct(count)
        unused = " [UNUSED]" if count == 0 else ""
        print(f"    {rule_name:<32} {count:>5} ({share:>5.1f}%){unused}")
    print()

    # Savings estimate
    llm_savings = no_abx + review
    time_per_pdf = 60  # seconds (average LLM call time)
    saved_time = llm_savings * time_per_pdf
    print(f"  {'Estimated LLM call savings:':<35} {llm_savings:>5}  (-{pct(llm_savings):.1f}%)")
    print(f"  {'Estimated time saved:':<35} {saved_time:.0f}s  ({saved_time/60:.1f}min / {saved_time/3600:.2f}h)")
    print(f"{'='*60}\n")


def _safe(text: Any, maxlen: int = 80) -> str:
    """Normalise to a printable, length-capped string.

    L-20: this round-tripped through cp1251, which cannot represent the corpus's
    own Cyrillic (Ё, ё, —, ≤ all became '?') and was used for BOTH the --audit
    output AND the `reason` field written into the manifests.
    """
    s = str(text) if text is not None else "?"
    return re.sub(r"\s+", " ", s).strip()[:maxlen]


def audit_no_antibiotics(results: list[dict], sample_size: int = 100, seed: int = 0):
    """Audit a random sample of items destined for archive_no_antibiotics.

    L-21: the sample was drawn with an unseeded ``random.sample``, so two runs
    over the same manifest audited DIFFERENT items and an audit could not be
    reproduced or challenged.  The default seed is fixed.
    """
    no_abx_items = [r for r in results if r["final_decision"] == "no_antibiotics"]

    if not no_abx_items:
        print("  No items destined for archive_no_antibiotics. Nothing to audit.")
        return True

    sample = random.Random(seed).sample(
        no_abx_items, min(sample_size, len(no_abx_items))
    )

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


def cmd_full_audit(move_files: bool = False) -> bool:
    """Full scan of all archive_no_antibiotics items.

    Returns True when nothing suspicious was found, False otherwise, so the CLI can
    exit non-zero.  M-36: the old docstring promised "Auto-move suspicious to
    review" while the body never moved a file; movement is now an explicit opt-in.
    """
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
    print(f"  These are being RE-CLASSIFIED to review in the dry-run manifest."
          if not move_files else
          f"  These are being MOVED to archive_review/.")
    if not move_files:
        # M-36: this function used to print "These will be moved to
        # archive_review/" while only rewriting `final_decision` in the dry-run
        # manifest.  NO FILE WAS EVER MOVED, so an operator who read the message
        # believed the corpus had been reclassified when it had not.
        print(f"  NOTE: --full-audit only updates dry_run_manifest.json; no PDF is moved.")
        print(f"        Run `python -m src.pipeline.prefilter --batch N` to actually move them.")

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
    print(f"\n  Updated dry_run_manifest.json: {updated} items re-classified to review.")

    moved = 0
    if move_files:
        create_directories()
        manifest: list[dict] = []
        for r in results:
            if r["Id"] in ids_to_move:
                moved += int(move_pdf(r, ARCHIVE_REVIEW, manifest))
        _append_movement_manifest(manifest)
        print(f"  Moved {moved} PDFs to archive_review/")

    print(f"\n  Action required: review these {len(suspicious)} items manually.")
    print(f"  After review, you can: python -m src.pipeline.prefilter --restore")
    return False


def cmd_audit(seed: int = 0) -> bool:
    if not DRY_RUN_MANIFEST.exists():
        print("  Dry run manifest not found. Run --dry-run first.")
        return True
    results = orjson.loads(DRY_RUN_MANIFEST.read_bytes())
    return audit_no_antibiotics(results, seed=seed)


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

    _append_movement_manifest(manifest)
    print(f"\n  Movement manifest appended: {MOVEMENT_MANIFEST}")
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

    _append_movement_manifest(manifest)
    print(f"\n  Movement manifest appended: {MOVEMENT_MANIFEST}")
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

    # M-37: drop the entries we just undone, so a later --restore does not try to
    # move files back from a location they no longer occupy.
    if restored and MOVEMENT_MANIFEST.exists():
        try:
            remaining = orjson.loads(MOVEMENT_MANIFEST.read_bytes())
        except Exception:
            remaining = []
        restored_sources = {str(Path(e["source_path"])) for e in manifest[:restored]}
        kept = [e for e in remaining if str(Path(e.get("source_path", ""))) not in restored_sources]
        MOVEMENT_MANIFEST.write_bytes(orjson.dumps(kept, option=orjson.OPT_INDENT_2))

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
    parser.add_argument("--full-audit", action="store_true",
                        help="Full scan all no_antibiotics items and re-classify suspicious to review")
    parser.add_argument("--move-suspicious", action="store_true",
                        help="with --full-audit: actually MOVE the suspicious PDFs to archive_review/")
    parser.add_argument("--batch", type=int, default=0, help="Move N PDFs as test batch")
    parser.add_argument("--all", action="store_true", help="Move all PDFs")
    parser.add_argument("--restore", action="store_true", help="Restore all PDFs from manifest")
    args = parser.parse_args()

    exit_code = 0
    if args.dry_run:
        cmd_dry_run()
    elif args.full_audit:
        # M-36: the verdict was discarded and the process always exited 0.
        ok = cmd_full_audit(move_files=args.move_suspicious)
        exit_code = 0 if ok else 1
    elif args.audit:
        ok = cmd_audit()
        exit_code = 0 if ok else 1
    elif args.batch > 0:
        cmd_move_batch(args.batch)
    elif args.all:
        cmd_move_all()
    elif args.restore:
        cmd_restore()
    else:
        parser.print_help()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
