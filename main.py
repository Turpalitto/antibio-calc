#!/usr/bin/env python3
"""ANTIBIO - CLI entry point.

Usage:
  python main.py doctor      # Project health check (read-only)
  python main.py sync        # Fix misplaced PDFs, regenerate manifest
  python main.py --help      # Full command list
"""

import argparse
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import orjson

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
for _p in [_HERE / "src" / "pipeline", _HERE / "src"]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

CR = Path(r"C:\clinrec_downloader")


# ── Helpers ──────────────────────────────────────────────────────────────


def _check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {label}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"     {line}")
    return ok


def _size_str(path: Path) -> str:
    s = path.stat().st_size
    if s < 1024:
        return f"{s} B"
    elif s < 1024 * 1024:
        return f"{s/1024:.0f} KB"
    else:
        return f"{s/1024/1024:.1f} MB"


def _safe(text: str, maxlen: int = 80) -> str:
    """Encode-safe truncation for cp1251 console."""
    s = str(text) if text else "?"
    return s.encode("cp1251", errors="replace").decode("cp1251")[:maxlen]


def _valid_json(path: Path):
    try:
        import orjson
        return orjson.loads(path.read_bytes())
    except Exception:
        return None


def _pdf_inventory():
    """Return {filename: [(label, Path), ...]} for all PDFs on disk."""
    result = {}
    for label in ["downloads_all", "downloads_active",
                   "archive_no_antibiotics", "archive_review"]:
        d = CR / label
        if d.exists():
            for f in d.glob("*.pdf"):
                result.setdefault(f.name, []).append((label, f))
    return result


def _load_clinrecs():
    f = CR / "clinrecs.json"
    return _valid_json(f) or []


def _load_dry():
    f = CR / "dry_run_manifest.json"
    return _valid_json(f) or []


def _load_manifest():
    f = CR / "movement_manifest.json"
    return _valid_json(f) or []


# ── Doctor ────────────────────────────────────────────────────────────────


def cmd_doctor():
    overall_ok = True
    t0 = time.monotonic()
    import orjson

    clinrecs = _load_clinrecs()
    dry = _load_dry()
    manifest = _load_manifest()
    pdfs = _pdf_inventory()

    print()
    print("=" * 60)
    print("  ANTIBIO - Health Check (doctor)")
    print("=" * 60)
    print(f"  Project root: {_HERE}")
    print(f"  Data dir:     {CR}")
    print()

    # ── 1. Directory structure ──
    print("---[ 1. Directory structure ]" + "-" * 35)
    for label in ["Project root", "Data root",
                  "downloads_all", "downloads_active",
                  "archive_no_antibiotics", "archive_review",
                  "DB (db/)", "Pipeline (src/pipeline/)",
                  "LLM (src/llm/)", "Tests (src/tests/)"]:
        if label in ("Project root", "Data root"):
            d = _HERE if label == "Project root" else CR
        elif label == "DB (db/)":
            d = _HERE / "db"
        elif label == "Pipeline (src/pipeline/)":
            d = _HERE / "src" / "pipeline"
        elif label == "LLM (src/llm/)":
            d = _HERE / "src" / "llm"
        elif label == "Tests (src/tests/)":
            d = _HERE / "src" / "tests"
        else:
            d = CR / label
        _check(label, d.exists())
    print()

    # ── 2. PDF inventory ──
    print("---[ 2. PDF inventory ]" + "-" * 39)
    dir_counts = {}
    total_pdf = 0
    for label in ["downloads_all", "downloads_active",
                   "archive_no_antibiotics", "archive_review"]:
        d = CR / label
        files = list(d.glob("*.pdf")) if d.exists() else []
        n = len(files)
        dir_counts[label] = n
        total_pdf += n
        _check(f"{label}/", True, f"{n} PDFs" if d.exists() else "NOT FOUND")
    _check("Total PDFs across all dirs", total_pdf > 0, f"{total_pdf} PDFs")

    if manifest:
        missing = [e for e in manifest if not Path(e["destination_path"]).exists()]
        _check("movement_manifest destinations", len(missing) == 0,
               f"All {len(manifest)} exist" if not missing else f"{len(missing)} missing on disk")
        if missing:
            overall_ok = False
    else:
        _check("movement_manifest.json", False, "NOT FOUND")
        overall_ok = False
    print()

    # ── 3. Configuration ──
    print("---[ 3. Configuration ]" + "-" * 39)
    try:
        from config import (
            CLINRECS_JSON, LLM_PROVIDER_CHAIN, LLM_PROVIDER_CONFIGS,
            EXTRACTION_MODEL, VALIDATION_MODEL,
        )
        _check("config.py imports", True)
        _check("CLINRECS_JSON", CLINRECS_JSON.exists(), f"{_size_str(CLINRECS_JSON)}")
        _check("LLM provider chain", True, f"{LLM_PROVIDER_CHAIN}")

        for name, cfg in LLM_PROVIDER_CONFIGS.items():
            key = cfg.get("api_key", "")
            has_key = bool(key) and not key.startswith("sk-placeholder")
            url = cfg.get("base_url", "N/A")
            model = cfg.get("model", "N/A")
            if has_key:
                _check(f"  {name}", True, f"{model} @ {url}")
            else:
                _check(f"  {name}", False, f"{model} @ {url} - NO API KEY")

        _check("Extraction model", True, EXTRACTION_MODEL)
        _check("Validation model", True, VALIDATION_MODEL)
    except Exception as e:
        _check("config.py", False, str(e))
        overall_ok = False
    print()

    # ── 4. Pipeline checkpoints ──
    print("---[ 4. Pipeline checkpoints ]" + "-" * 34)

    # extraction_progress.json
    ep = CR / "extraction_progress.json"
    ep_items = {}
    if ep.exists():
        data = _valid_json(ep)
        if data and isinstance(data, dict):
            ep_items = data.get("items", {})
            done = sum(1 for v in ep_items.values() if v.get("extraction_done"))
            failed = sum(1 for v in ep_items.values() if v.get("needs_reprocess"))
            _check("extraction_progress.json", True, f"{len(ep_items)} items, {done} done, {failed} reprocess")
        else:
            _check("extraction_progress.json", False, "Invalid JSON")
            overall_ok = False
    else:
        _check("extraction_progress.json", False, "NOT FOUND")
        overall_ok = False

    # extraction_raw.json
    er_path = CR / "extraction_raw.json"
    raw_data = _valid_json(er_path) if er_path.exists() else []
    extracted_cvs = set()
    if raw_data and isinstance(raw_data, list):
        for r in raw_data:
            gid = r.get("guideline_id") or r.get("code_version") or r.get("pdf_file")
            if gid:
                extracted_cvs.add(gid)
        _check("extraction_raw.json", True, f"{len(raw_data)} regimens, ~{len(extracted_cvs)} guidelines, {_size_str(er_path)}")
    elif er_path.exists():
        _check("extraction_raw.json", False, "Invalid JSON")
        overall_ok = False
    else:
        _check("extraction_raw.json", False, "NOT FOUND")
        overall_ok = False

    # extraction_validated.json
    ev = CR / "extraction_validated.json"
    if ev.exists():
        data = _valid_json(ev)
        _check("extraction_validated.json", True if data and isinstance(data, list) else False,
               f"{len(data)} regimens" if data and isinstance(data, list) else "Invalid JSON")
        if not data or not isinstance(data, list):
            overall_ok = False
    else:
        _check("extraction_validated.json", False, "NOT FOUND")
        overall_ok = False

    # knowledge_base.json
    kb_path = CR / "knowledge_base.json"
    kb_data = _valid_json(kb_path) if kb_path.exists() else []
    if kb_data and isinstance(kb_data, list):
        total_regimens = sum(len(g.get("regimens", [])) for g in kb_data)
        _check("knowledge_base.json", True, f"{len(kb_data)} guidelines, {total_regimens} regimens, {_size_str(kb_path)}")
    elif kb_path.exists():
        _check("knowledge_base.json", False, "Invalid JSON")
        overall_ok = False
    else:
        _check("knowledge_base.json", False, "NOT FOUND")
        overall_ok = False

    # metadata.sqlite
    ms = CR / "metadata.sqlite"
    sqlite_clinrecs = 0
    sqlite_regimens = 0
    if ms.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(ms))
            sqlite_clinrecs = conn.execute("SELECT COUNT(*) FROM clinrecs").fetchone()[0]
            sqlite_regimens = conn.execute("SELECT COUNT(*) FROM antibiotic_regimens").fetchone()[0]
            conn.close()
            _check("metadata.sqlite", True, f"{_size_str(ms)}, clinrecs: {sqlite_clinrecs}, regimens: {sqlite_regimens}")
        except Exception as e:
            _check("metadata.sqlite", False, str(e))
            overall_ok = False
    else:
        _check("metadata.sqlite", False, "NOT FOUND")
        overall_ok = False

    # dry_run_manifest.json
    if dry:
        decisions = {}
        for d in dry:
            dec = d.get("final_decision", "unknown")
            decisions[dec] = decisions.get(dec, 0) + 1
        detail = ", ".join(f"{k}={v}" for k, v in sorted(decisions.items()))
        _check("dry_run_manifest.json", True, f"{len(dry)} items, {detail}")
    else:
        _check("dry_run_manifest.json", False, "NOT FOUND")
        overall_ok = False
    print()

    # ── 5. LLM provider health ──
    print("---[ 5. LLM provider check ]" + "-" * 36)
    from config import LLM_PROVIDER_CHAIN, LLM_PROVIDER_CONFIGS
    for pname in LLM_PROVIDER_CHAIN:
        cfg = LLM_PROVIDER_CONFIGS.get(pname, {})
        url = cfg.get("base_url", "?")
        key = cfg.get("api_key", "")
        model = cfg.get("model", "?")
        has_key = bool(key) and not key.startswith("sk-placeholder")
        if not has_key:
            _check(f"  {pname}", False, f"{model} @ {url} - NO API KEY")
            overall_ok = False
            continue
        try:
            import httpx
            try:
                r = httpx.get(url, timeout=3.0)
                _check(f"  {pname}", True, f"reachable (HTTP {r.status_code}), {model}")
            except httpx.ConnectError:
                _check(f"  {pname}", False, f"{model} @ {url} - UNREACHABLE")
                overall_ok = False
            except httpx.TimeoutException:
                _check(f"  {pname}", False, f"{model} @ {url} - TIMEOUT")
                overall_ok = False
        except ImportError:
            _check(f"  {pname}", False, "httpx not installed")
    print()

    # ── 6. Pipeline readiness ──
    print("---[ 6. Pipeline readiness ]" + "-" * 35)
    from config import CLINRECS_JSON
    active_ids = {r["Id"] for r in dry if r.get("final_decision") == "need_llm"} if dry else set()
    ab_items = [i for i in clinrecs if i.get("abx_level") in ("A", "B")]
    remaining_active = []
    for i in ab_items:
        if i["Id"] not in active_ids:
            continue
        cv = i.get("CodeVersion") or f"{i.get('Code')}_{i.get('Version')}"
        if cv not in extracted_cvs:
            remaining_active.append(i)
    _check("Items in downloads_active/", True, f"{len(active_ids)} items")
    _check("Extracted guidelines (unique)", True, f"{len(extracted_cvs)} guidelines")
    if remaining_active:
        s = ", ".join(str(r["Id"]) for r in remaining_active[:10])
        if len(remaining_active) > 10:
            s += f", ... ({len(remaining_active)} total)"
        _check("Pipeline ready to resume", False, f"{len(remaining_active)} active items remain unextracted - need working LLM provider")
        overall_ok = False
    else:
        _check("Pipeline ready to resume", True, "All active items extracted, ready for validate + knowledge")
    print()

    # ── 7. DATA CONSISTENCY ──
    print("---[ 7. DATA CONSISTENCY ]" + "-" * 38)

    items_with_pdf = sum(1 for i in clinrecs if i.get("pdf_path"))
    items_no_pdf = len(clinrecs) - items_with_pdf
    clinrec_fnames = {Path(i["pdf_path"]).name for i in clinrecs if i.get("pdf_path")}
    missing_pdfs = clinrec_fnames - set(pdfs.keys())
    kb_pdf_refs = set()
    for g in (kb_data if isinstance(kb_data, list) else []):
        ref = g.get("pdf_file") or g.get("source_pdf") or ""
        if ref:
            kb_pdf_refs.add(ref)
    kb_missing = kb_pdf_refs - set(pdfs.keys())

    manifest_fnames = {Path(e["destination_path"]).name for e in manifest}
    orphans = set(pdfs.keys()) - manifest_fnames

    duplicate_names = {fn: locs for fn, locs in pdfs.items() if len(locs) > 1}

    # Misplaced items: dry_run_manifest vs actual location
    decision_to_dir = {
        "need_llm": "downloads_active",
        "no_antibiotics": "archive_no_antibiotics",
        "review": "archive_review",
    }
    misplaced = 0
    for d in dry:
        pp = d.get("pdf_path")
        if not pp:
            continue
        fname = Path(pp).name
        expected = decision_to_dir.get(d["final_decision"])
        actual = pdfs.get(fname, [])
        if expected and actual:
            actual_dirs = {loc[0] for loc in actual}
            if expected not in actual_dirs:
                misplaced += 1

    # SQLite vs KB mismatch
    sqlite_cvs = set()
    kb_cvs = set()
    if ms.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(ms))
            rows = conn.execute("SELECT code_version FROM clinrecs").fetchall()
            sqlite_cvs = {r[0] for r in rows if r[0]}
            conn.close()
        except Exception:
            pass
    for g in (kb_data if isinstance(kb_data, list) else []):
        cv = g.get("code_version") or ""
        if cv:
            kb_cvs.add(cv)
    # Only flag missing knowledge for A+B active items that should be in KB
    clinrec_by_id = {i["Id"]: i for i in clinrecs}
    active_ab_cvs = set()
    for d in dry:
        if d.get("final_decision") != "need_llm":
            continue
        cr = clinrec_by_id.get(d["Id"])
        if cr and cr.get("abx_level") in ("A", "B"):
            cv = cr.get("CodeVersion") or f"{cr.get('Code')}_{cr.get('Version')}"
            if cv:
                active_ab_cvs.add(cv)
    missing_knowledge = active_ab_cvs - kb_cvs

    print()
    print(f"  Clinical recommendations:    {len(clinrecs):>6}")
    print(f"    With pdf_path:             {items_with_pdf:>6}")
    print(f"    Without pdf_path:          {items_no_pdf:>6}")
    print(f"  Downloaded PDFs:             {total_pdf:>6}")
    print(f"    downloads_all/:            {dir_counts.get('downloads_all', 0):>6}")
    print(f"    downloads_active/:         {dir_counts.get('downloads_active', 0):>6}")
    print(f"    archive_no_antibiotics/:   {dir_counts.get('archive_no_antibiotics', 0):>6}")
    print(f"    archive_review/:           {dir_counts.get('archive_review', 0):>6}")
    print(f"  Processed in pipeline:       {len(extracted_cvs):>6} guidelines")
    print(f"  Knowledge records:           {len(kb_data) if isinstance(kb_data, list) else 0:>6}")
    print(f"  SQLite records:              {sqlite_clinrecs:>6} clinrecs, {sqlite_regimens} regimens")
    print(f"  Orphan files:                {len(orphans):>6}")
    print(f"  Duplicate filenames:         {len(duplicate_names):>6}")
    print(f"  Misplaced items:             {misplaced:>6}")
    print(f"  Missing PDFs (clinrecs ref): {len(missing_pdfs):>6}")
    print(f"  Broken KB refs:              {len(kb_missing):>6}")
    print(f"  Missing knowledge (active):  {len(missing_knowledge):>6}")

    consistency_ok = (
        len(orphans) == 0
        and len(duplicate_names) == 0
        and misplaced == 0
        and len(missing_pdfs) == 0
        and len(kb_missing) == 0
    )
    if not consistency_ok:
        overall_ok = False

    status = "PASS" if consistency_ok else "FAIL"
    print(f"  Data Consistency Status:     {status}")
    print()

    elapsed = time.monotonic() - t0
    print("=" * 60)
    final = "ALL CHECKS PASSED" if overall_ok else "SOME CHECKS FAILED"
    print(f"  {final} ({elapsed:.1f}s)")
    print("=" * 60)
    print()
    return 0 if overall_ok else 1


# ── Sync ─────────────────────────────────────────────────────────────────


def cmd_sync():
    """Fix misplaced PDFs: move to correct dir per dry_run_manifest, regenerate manifest."""
    import orjson
    from datetime import datetime, timezone

    print()
    print("=" * 60)
    print("  ANTIBIO - Sync (fix misplaced PDFs)")
    print("=" * 60)

    dry = _load_dry()
    manifest = _load_manifest()
    pdfs = _pdf_inventory()

    if not dry:
        print("  [FAIL] dry_run_manifest.json not found or empty")
        return 1

    decision_to_dir = {
        "need_llm": "downloads_active",
        "no_antibiotics": "archive_no_antibiotics",
        "review": "archive_review",
    }
    dir_to_path = {label: CR / label for label in decision_to_dir.values()}

    moved = 0
    skipped = 0
    errors = 0
    new_manifest = []

    for d in dry:
        pp = d.get("pdf_path")
        if not pp:
            continue
        fname = Path(pp).name
        expected_dir_label = decision_to_dir.get(d["final_decision"])
        if not expected_dir_label:
            continue
        expected_path = dir_to_path[expected_dir_label]
        actual = pdfs.get(fname, [])

        if not actual:
            skipped += 1
            continue

        actual_dirs = {loc[0] for loc in actual}
        if expected_dir_label in actual_dirs:
            # Already in correct place
            src = next((p for loc, p in actual if loc == expected_dir_label), actual[0][1])
            new_manifest.append({
                "source_path": str(CR / "downloads_all" / fname),
                "destination_path": str(src),
                "Id": d["Id"],
                "Name": d.get("Name"),
                "final_decision": d["final_decision"],
                "default_decision": d.get("default_decision"),
                "matched_rule": d.get("matched_rule"),
                "override": d.get("override", False),
                "reason": "synced (already correct)",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue

        # Need to move — pick the first source that still exists
        src = None
        for loc, path in actual:
            if path.exists():
                src = path
                break
        if src is None:
            # All copies already moved — check if destination has it now
            if expected_path.joinpath(fname).exists():
                print(f"  [OK]  {_safe(fname, 60)}: already at destination (duplicate)")
                new_manifest.append({
                    "source_path": str(CR / "downloads_all" / fname),
                    "destination_path": str(expected_path / fname),
                    "Id": d["Id"],
                    "Name": d.get("Name"),
                    "final_decision": d["final_decision"],
                    "default_decision": d.get("default_decision"),
                    "matched_rule": d.get("matched_rule"),
                    "override": d.get("override", False),
                    "reason": "synced (duplicate, already in place)",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue
            print(f"  [ERR] {_safe(fname, 60)}: source file not found")
            errors += 1
            continue

        dest = expected_path / fname
        if dest.exists():
            stem = src.stem
            suf = src.suffix
            dest = expected_path / f"{stem}_{d['Id']}{suf}"

        try:
            safe_name = _safe(fname, 60)
            print(f"  Moving: {safe_name} -> {expected_dir_label}/")
            shutil.move(str(src), str(dest))
            moved += 1
            new_manifest.append({
                "source_path": str(CR / "downloads_all" / fname),
                "destination_path": str(dest),
                "Id": d["Id"],
                "Name": d.get("Name"),
                "final_decision": d["final_decision"],
                "default_decision": d.get("default_decision"),
                "matched_rule": d.get("matched_rule"),
                "override": d.get("override", False),
                "reason": f"synced from {list(actual_dirs)[0]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            print(f"  [ERR] {_safe(fname, 60)}: {_safe(str(exc), 60)}")
            errors += 1

    # Save new manifest
    (CR / "movement_manifest.json").write_bytes(
        orjson.dumps(new_manifest, option=orjson.OPT_INDENT_2)
    )
    print()
    print(f"  Moved:    {moved}")
    print(f"  In-place: {len(new_manifest) - moved - errors}")
    print(f"  Skipped:  {skipped}")
    print(f"  Errors:   {errors}")
    print(f"  Manifest: {len(new_manifest)} entries")
    print()
    print("=" * 60)
    print(f"  {'ALL FILES SYNCED' if errors == 0 else 'SYNC COMPLETE WITH ERRORS'}")
    print("=" * 60)
    print()
    return 0 if errors == 0 else 1


# ── Conflict dedup ───────────────────────────────────────────────────────


def cmd_quarantine() -> int:
    """Move orphan files to quarantine/."""
    CR = Path(r"C:\clinrec_downloader")
    quarantine_dir = CR / "quarantine"
    quarantine_dir.mkdir(exist_ok=True)
    orphan_dir = CR / "downloads_all"

    # Build set of known filenames from manifest + clinrecs
    dry_path = CR / "dry_run_manifest.json"
    clinrecs_path = CR / "clinrecs.json"

    known = set()
    if dry_path.exists():
        dry = orjson.loads(dry_path.read_bytes())
        for d in dry:
            pp = d.get("pdf_path") or d.get("pdf_url")
            if pp:
                known.add(Path(pp).name)
    if clinrecs_path.exists():
        clin = orjson.loads(clinrecs_path.read_bytes())
        for c in clin:
            pp = c.get("pdf_path") or c.get("pdf_url")
            if pp:
                known.add(Path(pp).name)

    orphans = []
    for p in sorted(orphan_dir.iterdir()):
        if p.name not in known:
            orphans.append(p)

    if not orphans:
        print("  No orphan files found in downloads_all/")
        return 0

    print(f"  Found {len(orphans)} orphan file(s):")
    for p in orphans:
        size = p.stat().st_size if p.exists() else 0
        dest = quarantine_dir / p.name
        if dest.exists():
            stem = p.stem
            suf = p.suffix
            dest = quarantine_dir / f"{stem}_orphan{suf}"
        if p.exists():
            shutil.move(str(p), str(dest))
            print(f"    {p.name} ({size}B) -> quarantine/")
        else:
            print(f"    {p.name}: already moved or deleted")

    print(f"\n  Quarantine dir: {quarantine_dir}")
    return 0


def cmd_dedup() -> int:
    """Resolve conflicting duplicates in dry_run_manifest.

    Same filename → different final_decision across items.
    Strategy: unify to highest priority (need_llm > review > no_antibiotics).
    Never delete entries; log changes.
    """
    CR = Path(r"C:\clinrec_downloader")
    DRY = CR / "dry_run_manifest.json"
    REVIEW = CR / "review_required.json"

    dry = orjson.loads(DRY.read_bytes())

    # Index by filename
    from collections import defaultdict
    by_fname = defaultdict(list)
    for idx, d in enumerate(dry):
        pp = d.get("pdf_path") or d.get("pdf_url")
        if not pp:
            continue
        fname = Path(pp).name
        by_fname[fname].append((idx, d))

    priority = {"need_llm": 3, "review": 2, "no_antibiotics": 1}
    changes = []
    unresolved = []

    for fname, items in by_fname.items():
        decisions = {d["final_decision"] for _, d in items}
        if len(decisions) <= 1:
            continue

        # Highest priority wins
        winner = max(decisions, key=lambda x: priority.get(x, 0))

        for idx, d in items:
            old = d["final_decision"]
            if old != winner:
                d["final_decision"] = winner
                d["override"] = True
                d["matched_rule"] = "dedup_resolution"
                d["dedup_note"] = f"unified from {old} to {winner} (conflict, filename={fname})"
                changes.append({
                    "Id": d["Id"],
                    "filename": fname,
                    "old_decision": old,
                    "new_decision": winner,
                    "name": str(d.get("Name", ""))[:80],
                })

        # Check if ANY item in this conflict has a non-default decision (override or rule)
        has_override = any(d.get("override") or d.get("matched_rule", "default") != "default" for _, d in items)
        if not has_override and len(decisions) > 1:
            # All are default decisions — log to review_required
            unresolved.append({
                "filename": fname,
                "decisions": sorted({d["final_decision"] for _, d in items}),
                "item_ids": [d["Id"] for _, d in items],
                "resolved_to": winner,
                "reason": "automatic resolution (all defaults, no override)",
            })

    # Save updated dry_run_manifest
    DRY.write_bytes(orjson.dumps(dry, option=orjson.OPT_INDENT_2))
    print(f"  Conflicts resolved: {len(changes)} decisions fixed across {len(set(c['filename'] for c in changes))} filenames")

    # Save review_required
    if unresolved:
        existing = orjson.loads(REVIEW.read_bytes()) if REVIEW.exists() else []
        existing.extend(unresolved)
        REVIEW.write_bytes(orjson.dumps(existing, option=orjson.OPT_INDENT_2))
        print(f"  Review entries added: {len(unresolved)}")
    else:
        print("  No unresolved conflicts requiring manual review")

    print(f"  Total manifest entries: {len(dry)}")
    return 0


# ── CLI dispatch ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="ANTIBIO - research paper knowledge pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Pipeline commands (via python -m src.pipeline.main):
  python -m src.pipeline.main download
  python -m src.pipeline.main extract_raw
  python -m src.pipeline.main validate
  python -m src.pipeline.main knowledge
  python -m src.pipeline.main update
  python -m src.pipeline.main verify

Prefilter (via python -m src.pipeline.prefilter):
  python -m src.pipeline.prefilter --dry-run
  python -m src.pipeline.prefilter --full-audit
  python -m src.pipeline.prefilter --all
  python -m src.pipeline.prefilter --restore

Restore (via restore_archived_pdfs.py):
  python restore_archived_pdfs.py --preview
  python restore_archived_pdfs.py --ids 123,456

Sync:
  python main.py sync          # Fix misplaced PDFs, regenerate manifest
  python main.py dedup         # Resolve conflicting duplicates in dry_run_manifest
  python main.py quarantine    # Move orphan PDFs to quarantine/""",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    p = sub.add_parser("doctor", help="Project health check (read-only)")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("sync", help="Fix misplaced PDFs, regenerate manifest")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("dedup", help="Resolve conflicting duplicates in dry_run_manifest")
    p.set_defaults(func=cmd_dedup)

    p = sub.add_parser("quarantine", help="Move orphan PDFs to quarantine/")
    p.set_defaults(func=cmd_quarantine)

    args = parser.parse_args()
    if args.command == "doctor":
        return cmd_doctor()
    elif args.command == "sync":
        return cmd_sync()
    elif args.command == "dedup":
        return cmd_dedup()
    elif args.command == "quarantine":
        return cmd_quarantine()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
