"""RC-030 C7 Part II/XII -- regression tests for the queue reconciliation
and review-task readiness results. Runs against the real committed
`generated/rc030_c7/` artifacts (not fabricated fixtures) since the whole
point is to prove the real 113-task pool has zero duplicates and zero
blocked tasks, not to test an abstract algorithm in isolation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "generated" / "rc030_c7" / "master_registry.json"
BATCH_MANIFEST_PATH = ROOT / "review_batches" / "c7" / "batch_manifest.json"

pytestmark = pytest.mark.skipif(
    not REGISTRY_PATH.is_file(), reason="C7 generated registry not present in this checkout")


def _registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_zero_duplicate_validation_units():
    d = _registry()
    assert d["duplicate_appearances"] == 0
    assert d["duplicate_groups"] == []


def test_raw_and_unique_counts_match():
    d = _registry()
    assert d["raw_queue_total"] == d["unique_validation_units"] == d["final_unique_task_count"] == 113


def test_registry_keys_are_unique():
    d = _registry()
    keys = [(r["regimen_id"], r["regimen_version"]) for r in d["registry"]]
    assert len(keys) == len(set(keys))


def test_every_registry_entry_has_a_priority_and_primary_queue():
    d = _registry()
    for r in d["registry"]:
        assert r.get("primary_queue")
        assert isinstance(r.get("tags"), list) and r["primary_queue"] in r["tags"]


def test_batch_manifest_accounts_for_all_tasks():
    if not BATCH_MANIFEST_PATH.is_file():
        pytest.skip("batch manifest not present in this checkout")
    manifest = json.loads(BATCH_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["total_tasks"] == 113
    assert sum(b["task_count"] for b in manifest["batches"]) == 113
    all_ids = [uid for b in manifest["batches"] for uid in b["task_unit_ids"]]
    assert len(all_ids) == len(set(all_ids)), "a task_unit_id appears in more than one batch"
