#!/usr/bin/env python3
"""Explore clinrecs.json fields for prefilter design.

L-59: this whole script ran at MODULE SCOPE with no ``if __name__ ==
"__main__"`` guard, and imported a FLAT ``config`` that only resolves when
``src/pipeline`` happens to be on ``sys.path``.  Importing the module therefore
printed a report and raised ImportError -- which would break test collection if
anything ever imported it.  Everything now lives inside ``main()``.
"""
from collections import Counter
from pathlib import Path
from typing import Any


def _clinrecs_path() -> Path:
    """Locate clinrecs.json, preferring the pipeline config and falling back to argv."""
    import sys

    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    try:
        from config import CLINRECS_JSON  # noqa: PLC0415

        return Path(CLINRECS_JSON)
    except Exception:
        repo = Path(__file__).resolve().parents[2]
        for candidate in (
            repo / "tmp" / "clinrec_downloader" / "clinrecs.json",
            repo / "clinrecs.json",
        ):
            if candidate.is_file():
                return candidate
    raise FileNotFoundError("clinrecs.json not found; pass its path as the first argument")


def main() -> int:
    import orjson

    data: list[dict[str, Any]] = orjson.loads(_clinrecs_path().read_bytes())
    print(f"Total items: {len(data)}")
    if not data:
        return 0
    print(f"First item keys: {list(data[0].keys())}")
    print()

    for item in data[:3]:
        print(f"Id={item.get('Id')} Name={str(item.get('Name', ''))[:60]}")
        mkbs = item.get("Mkbs", [])
        mkb_str = "; ".join(
            f"{m.get('MkbCode', '')} {str(m.get('MkbName', ''))[:30]}" for m in mkbs
        ) if mkbs else "(none)"
        print(f"  MKB: {mkb_str}")
        print(f"  pdf_path: {item.get('pdf_path', '')}")
        print(f"  abx_level: {item.get('abx_level', '')}")
        print(f"  has_antibiotics: {item.get('has_antibiotics', 0)}")
        print(f"  category: {item.get('category', '')}")
        print()

    print(f"abx_level distribution: {dict(Counter(i.get('abx_level', '?') for i in data))}")
    print(f"category distribution: {dict(Counter(i.get('category', '?') for i in data))}")
    print(
        f"has_antibiotics distribution: "
        f"{dict(Counter(i.get('has_antibiotics', 0) for i in data))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
