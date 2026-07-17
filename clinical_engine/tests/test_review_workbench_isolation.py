"""RC-030 C6.7 Phase 0/13 — the Clinical Engine's "disconnected from RC-030 /
review governance" claim was, until now, only re-verified by ad-hoc grep in
report prose, never by an automated test. This closes that gap: the engine's
core modules must never import `review_workbench` (RC-030 owner-review
governance) or `dose_verification_sandbox` (the experimental RC-030 range
engine) -- neither is safe to wire into the authoritative recommendation
path without a real, separately-authorized migration.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_IMPORT_PREFIXES = ("review_workbench", "dose_verification_sandbox")

# Modules/packages whose import graph must stay clean. `review_workbench/`
# itself is excluded (it's allowed to import itself), as is this test file's
# own package and any test directory.
CHECKED_PATHS = ["engine.py", "pipeline.py", "config.py", "manifest.py", "models.py",
                 "terminology.py", "conformance.py", "readers", "api", "stages",
                 "regimen", "curated", "golden_cases", "bundles"]


def _iter_py_files():
    for rel in CHECKED_PATHS:
        p = ENGINE_ROOT / rel
        if p.is_file() and p.suffix == ".py":
            yield p
        elif p.is_dir():
            yield from p.rglob("*.py")


@pytest.mark.parametrize("py_file", list(_iter_py_files()), ids=lambda p: str(p.relative_to(ENGINE_ROOT)))
def test_engine_core_never_imports_review_workbench_or_sandbox(py_file: Path):
    text = py_file.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        for forbidden in FORBIDDEN_IMPORT_PREFIXES:
            if stripped.startswith((f"import {forbidden}", f"from {forbidden}")):
                raise AssertionError(
                    f"{py_file.relative_to(ENGINE_ROOT)} imports {forbidden!r} — "
                    f"Clinical Engine must stay disconnected from RC-030 review governance: {stripped!r}"
                )


def test_checked_paths_are_non_empty():
    """Guard against this test silently checking nothing if CHECKED_PATHS
    ever stops resolving to real files (e.g. after a directory rename)."""
    assert len(list(_iter_py_files())) > 10
