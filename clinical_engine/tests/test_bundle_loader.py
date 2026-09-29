"""P0-3 Bundle Loader tests (pure infrastructure only).

- Covers lifecycle, compat, integrity, registry, errors.
- No medical logic, no reader/provider imports, no antibiotic strings.
- Must pass with loader only + frozen manifest artifacts.
"""

from __future__ import annotations

import hashlib
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


def _write_payload(tmp: Path, body: str = '{"foo": 1}') -> Path:
    """Write the bundle payload at the primary candidate path and return it."""
    payload = tmp / "test-1.0.0.json"
    payload.write_text(body, encoding="utf-8")
    return payload


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_declared_content_hash_without_payload_is_rejected(tmp_path: Path) -> None:
    """A manifest-only load may no longer claim verification.

    This test previously asserted ``loaded.verified is True`` with the comment
    "no payload, skipped strict hash in baseline" -- the live test escape hatch
    that let a payload placed at a path the integrity-discovery list missed
    verify against nothing. ``content_hash`` is a required manifest field, so a
    declared hash with no payload is always a hard failure now.
    """
    mf = _write_manifest(tmp_path)
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(mf)
    assert exc.value.code == "PAYLOAD_NOT_FOUND"


def test_matching_payload_hash_verifies(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path)
    mf = _write_manifest(tmp_path, content_hash=_digest(payload))
    loaded = load_bundle(mf)
    assert loaded.verified is True
    assert loaded.resource == {"foo": 1}


def test_hash_mismatch_rejected(tmp_path: Path) -> None:
    mf = _write_manifest(tmp_path, content_hash="sha256:" + "0" * 64)
    payload = tmp_path / "test-1.0.0.json"
    payload.write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(mf)
    assert exc.value.code == "HASH_MISMATCH"


def test_sidecar_placed_payload_is_hashed_not_just_loaded(tmp_path: Path) -> None:
    """The documented sidecar convention is now hashed as well as loaded.

    The format handler loaded ``root.parent/f"{bundle_id}.json"`` while the
    integrity check hashed a different, disagreeing list, so a payload at the
    sidecar path was served with its declared content_hash never compared.
    """
    root = tmp_path / "bundle_root"
    root.mkdir()
    sidecar = tmp_path / "test-1.0.0.json"
    sidecar.write_text('{"foo": 1}', encoding="utf-8")
    mf = _write_manifest(root, content_hash=_digest(sidecar))
    assert not (root / "test-1.0.0.json").exists()

    loaded = load_bundle(mf)
    assert loaded.resource == {"foo": 1}
    assert loaded.verified is True

    sidecar.write_text('{"foo": 2}', encoding="utf-8")
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(mf)
    assert exc.value.code == "HASH_MISMATCH"


def test_incompatible_kernel_rejected(tmp_path: Path) -> None:
    mf = _write_manifest(tmp_path, requires_kernel="99.0")
    with pytest.raises(BundleLoadError) as exc:
        BundleLoader(engine_version="1.0.0").load(mf)
    assert exc.value.code == "INCOMPATIBLE_KERNEL"


def test_requires_kernel_compatibility_is_a_hard_check(tmp_path: Path) -> None:
    """A kernel-compatibility failure used to be able to degrade to a warning
    (``except (ValueError, IndexError)`` swallowed the parse and continued), and
    a non-numeric ``engine_version`` was never validated at all."""
    payload = _write_payload(tmp_path)
    mf = _write_manifest(tmp_path, requires_kernel="2.5", content_hash=_digest(payload))
    with pytest.raises(BundleLoadError) as exc:
        BundleLoader(engine_version="1.9.9").load(mf)
    assert exc.value.code == "INCOMPATIBLE_KERNEL"
    with pytest.raises(BundleLoadError) as exc:
        BundleLoader(engine_version="one-point-oh").load(mf)
    assert exc.value.code == "UNPARSEABLE_ENGINE_VERSION"


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
    payload = _write_payload(tmp_path)
    mf = _write_manifest(tmp_path, bundle_format="custom-test", content_hash=_digest(payload))
    loaded = load_bundle(mf)
    assert loaded.resource == {"loaded": "via-custom", "id": "test-1.0.0"}


def test_expired_bundle_is_rejected_not_warned(tmp_path: Path) -> None:
    """Expiry was only a warning, so an expired bundle loaded with
    verified=True and was indistinguishable from a current one."""
    payload = _write_payload(tmp_path)
    mf = _write_manifest(tmp_path, expiry="2000-01-01", content_hash=_digest(payload))
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(mf)
    assert exc.value.code == "BUNDLE_EXPIRED"


def test_unexpired_bundle_loads_without_warnings(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path)
    mf = _write_manifest(tmp_path, expiry="2999-01-01", content_hash=_digest(payload))
    assert load_bundle(mf).warnings == ()


def test_ambiguous_manifest_directory_is_rejected(tmp_path: Path) -> None:
    """``manifests[0]`` from a glob had no tie-break, so a directory holding two
    manifests loaded an arbitrary one depending on filesystem order."""
    root = tmp_path / "ambiguous"
    root.mkdir()
    _write_manifest(root)
    (root / "manifest.json").write_text(
        (root / "test_bundle_manifest.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(root)
    assert exc.value.code == "MANIFEST_AMBIGUOUS"


def test_loaded_bundle_fields(tmp_path: Path) -> None:
    payload = _write_payload(tmp_path)
    mf = _write_manifest(tmp_path, content_hash=_digest(payload))
    loaded = load_bundle(mf)
    assert loaded.bundle_path.exists()
    assert isinstance(loaded, LoadedBundle)
    assert isinstance(loaded.manifest, BundleManifest)
    assert loaded.manifest is not None
    assert isinstance(loaded.resource, dict)  # default handler


def test_loader_rejects_non_boolean_strict() -> None:
    with pytest.raises(ValueError):
        BundleLoader(strict="no")  # type: ignore[arg-type]


def test_load_bundle_honours_engine_version() -> None:
    """``load_bundle`` silently dropped the ``engine_version`` it was given and
    always used the loader default."""
    base = Path(__file__).resolve().parent.parent / "resources"
    mf = base / "score_profile_bundle_manifest.json"
    if not mf.exists():
        pytest.skip("no shipped score profile manifest")
    with pytest.raises(BundleLoadError) as exc:
        load_bundle(mf, engine_version="0.9.0")
    assert exc.value.code == "INCOMPATIBLE_KERNEL"
    assert load_bundle(mf, engine_version="1.0.0").verified is True


def test_pure_infra_no_medical_imports() -> None:
    """Sanity: loader module does not pull clinical domain."""
    import clinical_engine.bundles.loader as L
    src = Path(L.__file__).read_text(encoding="utf-8")
    forbidden = ["diagnosis", "regimen", "drug", "safety", "dose", "allergy", "pregnancy", "clinical"]
    src_clean = src.lower().replace("clinical_engine", "")
    for word in forbidden:
        assert word not in src_clean, f"medical word leaked: {word}"


def test_p04_real_wrapped_manifests_load_and_verify() -> None:
    """P0-4 migration smoke: a real manifest whose payload IS shipped loads and
    verifies against its declared hash.

    The safety/terminology/regimen manifests declare a content_hash for a payload
    that is not shipped next to them (the regimen manifest even documents this:
    "sqlite payload external"). Under the previous "no payload -> verified=True"
    escape hatch they reported themselves as verified. They now fail closed;
    :func:`test_manifest_without_shipped_payload_fails_closed` asserts that.
    """
    base = Path(__file__).resolve().parent.parent / "resources"
    score_mf = base / "score_profile_bundle_manifest.json"
    if score_mf.exists():
        loaded = load_bundle(score_mf)
        assert loaded.manifest.bundle_type == "score_profile"
        assert loaded.verified is True
        assert loaded.resource  # the shipped score_profiles/default.json was loaded


def test_manifest_without_shipped_payload_fails_closed() -> None:
    """A declared content_hash with no shipped payload is PAYLOAD_NOT_FOUND, not
    verified=True."""
    base = Path(__file__).resolve().parent.parent / "resources"
    for name, bundle_type in (
        ("safety_bundle_manifest.json", "safety"),
        ("terminology_bundle_manifest.json", "terminology"),
        ("regimen_bundle_manifest.json", "regimen"),
    ):
        mf = base / name
        if not mf.exists():
            continue
        with pytest.raises(BundleLoadError) as exc:
            load_bundle(mf)
        assert exc.value.code == "PAYLOAD_NOT_FOUND", name


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
    """Default load unchanged; check_conformance opt-in only.

    Uses the score-profile manifest, the one shipped manifest that carries its
    payload. The regimen manifest declares a hash for an external (unshipped)
    sqlite payload, so it no longer loads at all -- see
    :func:`test_manifest_without_shipped_payload_fails_closed`.
    """
    base = Path(__file__).resolve().parent.parent / "resources"
    mf = base / "score_profile_bundle_manifest.json"
    if mf.exists():
        loaded_default = load_bundle(mf)  # default False
        assert loaded_default.conformance is None

        loaded_checked = load_bundle(mf, check_conformance=True)
        assert loaded_checked.conformance is not None


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
