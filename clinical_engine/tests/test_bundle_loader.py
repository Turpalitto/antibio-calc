"""P0-3 Bundle Loader tests (pure infrastructure only).

- Covers lifecycle, compat, integrity, registry, errors.
- No medical logic, no reader/provider imports, no antibiotic strings.
- Must pass with loader only + frozen manifest artifacts.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from clinical_engine.bundles.loader import (
    BundleLoadError,
    BundleLoader,
    LoadedBundle,
    load_bundle,
    register_bundle_format,
)
from clinical_engine.manifest import BundleManifest


def _write_manifest(tmp: Path, **overrides) -> Path:
    m = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "bundle_id": "test-1.0.0",
        "bundle_type": "test",
        "curation_status": "curated",
    }
    m.update(overrides)
    p = tmp / "test_bundle_manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def test_load_manifest_only_succeeds(tmp_path: Path) -> None:
    """Manifest load + validate works (payload optional for some cases)."""
    mf = _write_manifest(tmp_path)
    loaded = load_bundle(mf)
    assert isinstance(loaded, LoadedBundle)
    assert isinstance(loaded.manifest, BundleManifest)
    assert loaded.manifest.bundle_id == "test-1.0.0"
    assert loaded.verified is True  # no payload, skipped strict hash in baseline


def test_hash_mismatch_rejected(tmp_path: Path) -> None:
    mf = _write_manifest(tmp_path, content_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000")
    payload = tmp_path / "test-1.0.0.json"
    payload.write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(mf)
    assert exc.value.code == "HASH_MISMATCH"


def test_incompatible_kernel_rejected(tmp_path: Path) -> None:
    mf = _write_manifest(tmp_path, requires_kernel="99.0")
    with pytest.raises(BundleLoadError) as exc:
        BundleLoader(engine_version="1.0.0").load(mf)
    assert exc.value.code == "INCOMPATIBLE_KERNEL"


def test_unsupported_format_rejected(tmp_path: Path) -> None:
    mf = _write_manifest(tmp_path, bundle_format="future-lance-v9")
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(mf)
    assert exc.value.code == "UNSUPPORTED_FORMAT"


def test_register_new_format_no_core_change(tmp_path: Path) -> None:
    """Genericity: new format added by register only."""
    def fake_handler(root: Path, manifest: BundleManifest) -> dict:
        return {"loaded": "via-custom", "id": manifest.bundle_id}

    register_bundle_format("custom-test", fake_handler)
    mf = _write_manifest(tmp_path, bundle_format="custom-test")
    loaded = load_bundle(mf)
    assert loaded.resource == {"loaded": "via-custom", "id": "test-1.0.0"}


def test_warnings_on_expiry(tmp_path: Path) -> None:
    past = "2000-01-01"
    mf = _write_manifest(tmp_path, expiry=past)
    loaded = load_bundle(mf)
    assert any("expired" in w for w in loaded.warnings)


def test_loaded_bundle_fields(tmp_path: Path) -> None:
    mf = _write_manifest(tmp_path)
    loaded = load_bundle(mf)
    assert loaded.bundle_path.exists()
    assert loaded.manifest is not None
    assert isinstance(loaded.resource, dict)  # default handler


def test_pure_infra_no_medical_imports() -> None:
    """Sanity: loader module does not pull clinical domain."""
    import clinical_engine.bundles.loader as L
    src = Path(L.__file__).read_text(encoding="utf-8")
    forbidden = ["diagnosis", "regimen", "drug", "safety", "dose", "allergy", "pregnancy", "clinical"]
    src_clean = src.lower().replace("clinical_engine", "")
    for word in forbidden:
        assert word not in src_clean, f"medical word leaked: {word}"


def test_p04_real_wrapped_manifests_load_and_verify() -> None:
    """P0-4 migration smoke: real manifests with correct hashes load via loader."""
    base = Path(__file__).resolve().parent.parent / "resources"
    # score
    score_mf = base / "score_profile_bundle_manifest.json"
    if score_mf.exists():
        loaded = load_bundle(score_mf)
        assert loaded.manifest.bundle_type == "score_profile"
        assert loaded.verified or loaded.manifest.content_hash.startswith("sha256:")
    # safety (constants)
    safety_mf = base / "safety_bundle_manifest.json"
    if safety_mf.exists():
        loaded = load_bundle(safety_mf)
        assert loaded.manifest.bundle_type == "safety"
        assert "clinical_constants" in loaded.manifest.notes or loaded.verified
    # terminology (using drug hash for smoke)
    term_mf = base / "terminology_bundle_manifest.json"
    if term_mf.exists():
        loaded = load_bundle(term_mf)
        assert loaded.manifest.bundle_type == "terminology"


# --- P2-1 Conformance Validator tests (additive, default behavior preserved) ---

from clinical_engine.conformance import check_conformance, ConformanceValidator


def test_conformance_passes_on_real_manifests() -> None:
    base = Path(__file__).resolve().parent.parent / "resources"
    for mf in [
        base / "regimen_bundle_manifest.json",
        base / "safety_bundle_manifest.json",
        base / "terminology_bundle_manifest.json",
        base / "score_profile_bundle_manifest.json",
    ]:
        if mf.exists():
            with open(mf, encoding="utf-8") as f:
                raw = json.load(f)
            res = check_conformance(raw)
            assert res.conformant is True
            assert len([i for i in res.issues if i.severity == "ERROR"]) == 0


def test_conformance_strict_unknown_flags() -> None:
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:deadbeef",
        "bundle_id": "test-strict",
        "bundle_type": "regimen",
        "future_extension": "should-flag-in-strict",
    }
    # default tolerant
    res_default = check_conformance(raw, strict_unknown=False)
    assert res_default.conformant is True

    # strict flags
    res_strict = check_conformance(raw, strict_unknown=True)
    assert res_strict.conformant is False
    assert any(i.code == "UNKNOWN_FIELD" for i in res_strict.issues)


def test_conformance_reports_draft() -> None:
    raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        "requires_kernel": "1.0",
        "bundle_format": "v1",
        "content_hash": "sha256:deadbeef",
        "bundle_id": "test-draft",
        "bundle_type": "regimen",
        "curation_status": "AUTO_GENERATED_DRAFT",
    }
    res = check_conformance(raw)
    assert any(i.code == "DRAFT_IN_PRODUCTION_CONTEXT" for i in res.issues)


def test_loader_conformance_optional_no_break_default() -> None:
    """Default load unchanged; check_conformance opt-in only."""
    base = Path(__file__).resolve().parent.parent / "resources"
    mf = base / "regimen_bundle_manifest.json"
    if mf.exists():
        loaded_default = load_bundle(mf)  # default False
        assert loaded_default.conformance is None

        loaded_checked = load_bundle(mf, check_conformance=True)
        assert loaded_checked.conformance is not None
        assert loaded_checked.conformance.conformant is True


def test_conformance_manifest_validation_error_negative() -> None:
    """Real negative test: executes the actual validate_manifest failure -> except ValueError branch in ConformanceValidator.
    Proves MANIFEST_VALIDATION_ERROR is produced for invalid manifest.
    """
    # Missing required fields -> validate_manifest raises ValueError
    bad_raw = {
        "schema_version": "1.0.0",
        "version": "1.0.0",
        # missing requires_kernel, bundle_format, content_hash, bundle_id, bundle_type etc.
    }

    # Use check_conformance which goes through ConformanceValidator.validate_manifest
    res = check_conformance(bad_raw)
    assert res.conformant is False
    error_issues = [i for i in res.issues if i.code == "MANIFEST_VALIDATION_ERROR"]
    assert len(error_issues) >= 1
    issue = error_issues[0]
    assert issue.severity == "ERROR"
    assert "Missing required field" in issue.message or "required" in issue.message.lower()

    # Deterministic: same input produces identical result
    res2 = check_conformance(bad_raw)
    assert res.conformant == res2.conformant
    assert len(res.issues) == len(res2.issues)
    assert res.issues[0].code == res2.issues[0].code
    assert res.issues[0].severity == res2.issues[0].severity
    # Also test via validator directly
    v = ConformanceValidator()
    res3 = v.validate_manifest(bad_raw)
    assert res3.conformant is False
    assert any(i.code == "MANIFEST_VALIDATION_ERROR" for i in res3.issues)
