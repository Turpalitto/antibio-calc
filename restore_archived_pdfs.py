#!/usr/bin/env python3
"""restore_archived_pdfs.py — Восстановление PDF из архива.

Использование:
  python restore_archived_pdfs.py              # полное восстановление
  python restore_archived_pdfs.py --preview    # просмотр без восстановления
  python restore_archived_pdfs.py --ids 690,697,866  # восстановить только указанные
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from collections import Counter

MANIFEST = Path(__file__).parent / ".." / "clinrec_downloader" / "movement_manifest.json"
# Also check alternative location
MANIFEST_ALT = Path(__file__).parent / ".." / "clinrec_downloader" / "dry_run_manifest.json"


def load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    import orjson
    return orjson.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description="Restore archived PDFs to original locations")
    parser.add_argument("--preview", action="store_true", help="Show what would be restored")
    parser.add_argument("--ids", type=str, default="", help="Comma-separated list of Ids to restore")
    parser.add_argument("--source", type=str, default="",
                        help="Path to movement_manifest.json (auto-detected if omitted)")
    args = parser.parse_args()

    # Find manifest
    candidates = []
    if args.source:
        candidates.append(Path(args.source))
    else:
        candidates = [MANIFEST]
        # Search in parent dirs
        for p in [Path(__file__).parent, Path(__file__).parent.parent,
                  Path(__file__).parent.parent / "clinrec_downloader"]:
            for fname in ["movement_manifest.json", "dry_run_manifest.json"]:
                f = p / fname
                if f.exists() and f not in candidates:
                    candidates.append(f)

    manifest = None
    for c in candidates:
        m = load_manifest(c)
        if m:
            manifest = m
            print(f"Loaded manifest: {c} ({len(m)} entries)")
            break

    if not manifest:
        print("No manifest found. Checked:")
        for c in candidates:
            print(f"  - {c}")
        sys.exit(1)

    # Filter by IDs if specified
    if args.ids:
        ids_to_restore = {int(x.strip()) for x in args.ids.split(",") if x.strip().isdigit()}
        filtered = [e for e in manifest if e.get("Id") in ids_to_restore]
        skipped = [e for e in manifest if e.get("Id") not in ids_to_restore]
        print(f"Filtered: {len(filtered)} to restore, {len(skipped)} skipped")
        manifest = filtered

    if args.preview:
        print(f"\nPreview: {len(manifest)} files to restore\n")
        stats = Counter(e.get("final_decision", "unknown") for e in manifest)
        for decision, count in stats.most_common():
            print(f"  {decision}: {count}")
        print()
        for entry in manifest[:20]:
            src = Path(entry.get("destination_path", ""))
            dst = Path(entry.get("source_path", ""))
            name = entry.get("Name", "?")[:50]
            print(f"  [{entry.get('Id', '?')}] {name}")
            print(f"       {src.name} -> {dst.parent.name}/")
        if len(manifest) > 20:
            print(f"  ... and {len(manifest) - 20} more")
        return

    # Perform restore
    restored = 0
    errors = 0
    for entry in manifest:
        src = Path(entry.get("destination_path", ""))
        dst = Path(entry.get("source_path", ""))

        if not src.exists():
            print(f"  NOT FOUND: {src}")
            errors += 1
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        restored += 1

    print(f"\nRestored: {restored} files")
    print(f"Errors:   {errors}")

    if restored == len(manifest):
        print(f"\nAll {restored} files returned to original locations.")

        # Clean up empty archive dirs
        for d in ["downloads_active", "archive_no_antibiotics", "archive_review"]:
            p = Path(__file__).parent.parent / "clinrec_downloader" / d
            if p.exists():
                remaining = list(p.iterdir())
                if not remaining:
                    p.rmdir()
                    print(f"  Removed empty directory: {d}/")
                else:
                    print(f"  Warning: {d}/ still has {len(remaining)} files (not in manifest)")


if __name__ == "__main__":
    main()
