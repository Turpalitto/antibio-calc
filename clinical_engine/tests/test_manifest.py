"""Unit tests for BundleManifest (P0-1).

Tests the schema, validator, loader exactly per frozen RFC.
No changes to architecture or other modules.
"""

import json
from pathlib import Path

import pytest

from clinical_engine.manifest import (
    BundleManifest,
    load_manifest,
    validate_manifest,
)


RESOURCES = Path(__file__).parent.parent / "resources"


def test_schema_loads():
    schema_path = RESOURCES / "bundle_manifest.schema.json"
    assert schema_path.exists()
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    assert schema["title"] == "BundleManifest"
    assert "schema_version" in schema["properties"]
    assert "requires_kernel" in schema["properties"]


def test_valid_regimen_manifest():
    path = RESOURCES / "regimen_bundle_manifest.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    validate_manifest(raw)
    m = load_manifest(raw)
    assert isinstance(m, BundleManifest)
    assert m.bundle_type == "regimen"
    assert m.requires_kernel == "1.0"
    assert m.content_hash.startswith("sha256:")
    assert len(m.source_refs) > 0


def test_valid_safety_manifest():
    path = RESOURCES / "safety_bundle_manifest.json"
    m = load_manifest(path)
    assert m.bundle_type == "safety"
    assert m.curation_status == "curated"


def test_valid_terminology_manifest():
    path = RESOURCES / "terminology_bundle_manifest.json"
    m = load_manifest(path)
    assert m.bundle_type == "terminology"
    assert "ATC" in m.source_refs[0]


def test_valid_score_profile_manifest():
    path = RESOURCES / "score_profile_bundle_manifest.json"
    m = load_manifest(path)
    assert m.bundle_type == "score_profile"
    assert m.stats is not None


def test_missing_required_raises():
    raw = {"schema_version": "1.0.0", "version": "1.0.0"}  # missing several
    with pytest.raises(ValueError, match="Missing required"):
        validate_manifest(raw)


def test_content_hash_format():
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "badformat",  # no colon
        "bundle_id": "test",
        "bundle_type": "regimen",
    }
    with pytest.raises(ValueError, match="does not match pattern"):
        validate_manifest(raw)


def test_i10_ignores_unknown_fields():
    """Per I10 Forward Compatibility: unknown optional fields must not cause rejection."""
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:deadbeef",
        "bundle_id": "test-i10",
        "bundle_type": "regimen",
        "future_unknown_field": "ignored",
        "another_extension": {"nested": 123},
    }
    # Should not raise
    validate_manifest(raw)
    m = load_manifest(raw)
    # Unknown fields are not present in the dataclass (dropped)
    assert not hasattr(m, "future_unknown_field")
    assert m.bundle_id == "test-i10"


def test_unknown_bundle_type_tolerated_i10():
    """Unknown bundle_type tolerated per I10 (no hard enum reject in base validator)."""
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:abc123",
        "bundle_id": "test",
        "bundle_type": "future_bundle_type_xyz",
    }
    validate_manifest(raw)  # must not raise for unknown type


def test_load_from_file_and_string():
    path = RESOURCES / "regimen_bundle_manifest.json"
    m1 = load_manifest(path)
    raw = path.read_text(encoding="utf-8")
    m2 = load_manifest(raw)
    assert m1.bundle_id == m2.bundle_id


def test_signatures_require_algorithm():
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:abc",
        "bundle_id": "sigtest",
        "bundle_type": "regimen",
        "signatures": [{"value": "onlyvalue"}],  # missing algorithm
    }
    with pytest.raises(ValueError, match="algorithm"):
        validate_manifest(raw)


# Additional: roundtrip and basic structure
def test_manifest_roundtrip_minimal():
    minimal = {
        "schema_version": "1.0.0",
        "version": "0.0.1",
        "requires_kernel": "0.1",
        "bundle_format": "v1",
        "content_hash": "sha256:0123456789abcdef",
        "bundle_id": "minimal-test",
        "bundle_type": "constants",
    }
    m = load_manifest(minimal)
    assert m.schema_version == "1.0.0"
    assert m.bundle_type == "constants"
    assert m.curation_status is None  # optional


# ============================================================
# Six mandatory negative / coverage tests from Acceptance Review
# ============================================================

def test_invalid_schema_version():
    """Invalid schema_version format must be rejected."""
    raw = {
        "schema_version": "1.0",  # invalid semver
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:abc123",
        "bundle_id": "test",
        "bundle_type": "regimen",
    }
    with pytest.raises(ValueError, match="does not match pattern"):
        validate_manifest(raw)


def test_invalid_requires_kernel():
    """Invalid requires_kernel format must be rejected."""
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1",  # invalid
        "bundle_format": "v1",
        "content_hash": "sha256:abc123",
        "bundle_id": "test",
        "bundle_type": "regimen",
    }
    with pytest.raises(ValueError, match="does not match pattern"):
        validate_manifest(raw)


def test_invalid_dependency_declarations():
    """depends_on must be list of strings."""
    # non-list
    raw1 = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:abc123",
        "bundle_id": "test",
        "bundle_type": "regimen",
        "depends_on": "not-a-list",
    }
    with pytest.raises(ValueError):
        validate_manifest(raw1)

    # list with non-string
    raw2 = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:abc123",
        "bundle_id": "test",
        "bundle_type": "regimen",
        "depends_on": [123],
    }
    with pytest.raises(ValueError, match="items must be strings"):
        validate_manifest(raw2)


def test_malformed_signatures_more_cases():
    """More cases for malformed signatures."""
    base = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:abc123",
        "bundle_id": "test",
        "bundle_type": "regimen",
    }

    # signatures not a list
    raw1 = {**base, "signatures": "not-a-list"}
    with pytest.raises(ValueError):
        validate_manifest(raw1)

    # signature item missing "value"
    raw2 = {**base, "signatures": [{"algorithm": "ed25519"}]}
    with pytest.raises(ValueError, match="algorithm"):
        validate_manifest(raw2)

    # signature item is not a dict
    raw3 = {**base, "signatures": ["bad"]}
    with pytest.raises(ValueError):
        validate_manifest(raw3)


def test_unknown_bundle_format_accepted():
    """Arbitrary bundle_format must be accepted (I10)."""
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "future_format_xyz_v99",
        "content_hash": "sha256:abc123",
        "bundle_id": "test",
        "bundle_type": "regimen",
    }
    validate_manifest(raw)  # must not raise
    m = load_manifest(raw)
    assert m.bundle_format == "future_format_xyz_v99"


def test_full_example_loads_all_optional_fields():
    """Full example must correctly populate all optional fields."""
    path = RESOURCES / "regimen_bundle_manifest.json"
    m = load_manifest(path)

    assert m.supersedes == ["regimens-main-1.1.0"]
    assert m.expiry == "2027-12-31"
    assert m.freshness_policy == {
        "max_age_days": 365,
        "must_refresh_before": "2027-01-01"
    }
    assert m.stats == {
        "regimen_count": 2675,
        "guideline_count": 294,
        "diagnosis_count": 72
    }
    assert m.notes is not None and "Level A" in m.notes
    assert m.curation_status == "curated"
    assert m.generated_by is not None
    assert m.jurisdiction == "RU"
    assert m.specialty == "infectious_diseases"
    assert len(m.signatures) == 1
    assert m.depends_on == ["terminology-atc-1.0.0"]
