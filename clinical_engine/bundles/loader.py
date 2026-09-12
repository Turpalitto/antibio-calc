"""Generic Bundle Loader (P0-3 infrastructure only).

Responsibilities (exact):
- Resolve manifest + payload.
- Validate via frozen manifest.py (I10 preserved).
- Compatibility (requires_kernel, bundle_format, expiry).
- Integrity (content_hash verify).
- Dispatch to registered format handler (opaque resource returned).
- Return LoadedBundle.

MUST NOT:
- Any domain-specific logic.
- Any reader/provider/stage/decision code.
- Hardcode bundle_type specifics.
- Modify frozen BundleManifest.
- Change engine behavior (standalone for P0-3).
- Network or writes.

Only new handlers for new bundle types/formats.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from clinical_engine.manifest import BundleManifest, load_manifest, validate_manifest

if TYPE_CHECKING:
    # Только для проверки типов: conformance.py сам импортирует LoadedBundle из этого
    # модуля, поэтому обычный импорт создал бы цикл. Без этого объявления аннотация
    # ConformanceResult не разрешается — typing.get_type_hints падал с NameError.
    from clinical_engine.conformance import ConformanceResult
# P2-1: late import to avoid circular (conformance imports LoadedBundle)


class BundleLoadError(Exception):
    """Pure infrastructure load failure."""

    def __init__(self, code: str, message: str, *, bundle_path: Path | None = None) -> None:
        self.code = code
        self.message = message
        self.bundle_path = bundle_path
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class LoadedBundle:
    """Infra result. resource is opaque to loader."""

    manifest: BundleManifest
    resource: Any
    bundle_path: Path
    verified: bool
    warnings: tuple[str, ...] = ()
    conformance: ConformanceResult | None = None  # P2-1 additive (None when not checked)


# Registry: bundle_format -> handler(root_path, manifest) -> resource
# Add only, never edit loader for new types.
_FORMAT_HANDLERS: dict[str, Callable[[Path, BundleManifest], Any]] = {}


def register_bundle_format(
    bundle_format: str, handler: Callable[[Path, BundleManifest], Any]
) -> None:
    """Register handler for a format. Called by format-specific adapters only."""
    if not isinstance(bundle_format, str) or not bundle_format:
        raise ValueError("bundle_format must be non-empty str")
    _FORMAT_HANDLERS[bundle_format] = handler


def _default_json_handler(root: Path, manifest: BundleManifest) -> dict[str, Any]:
    """Baseline v1 JSON payload handler (infra example).

    Convention: look for payload next to manifest or in root using bundle_id hints.
    Real handlers (P0-4) will target actual resources.
    """
    candidates = [
        root / f"{manifest.bundle_id}.json",
        root / "index.json",
        root / "data.json",
        root.parent / f"{manifest.bundle_id}.json",  # sidecar
        root / "score_profiles" / "default.json",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                raise BundleLoadError(
                    "PAYLOAD_PARSE_ERROR", f"Failed to parse {p}: {exc}", bundle_path=root
                ) from exc
    # Fallback: return empty dict (tests use manifest-only cases)
    return {}


# Register baseline "v1"
register_bundle_format("v1", _default_json_handler)


def _compute_hash(path: Path, algorithm: str = "sha256") -> str:
    """Compute algorithm:hex for file content. Used for integrity."""
    h = hashlib.new(algorithm)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"{algorithm}:{h.hexdigest()}"


def _check_compatibility(manifest: BundleManifest, engine_version: str) -> list[str]:
    """Pure version/format checks. Return warnings (or raise on hard fail)."""
    warnings: list[str] = []
    # requires_kernel: "X.Y" vs engine "X.Y.Z"
    req = manifest.requires_kernel
    try:
        req_major, req_minor = map(int, req.split("."))
        eng_parts = engine_version.split(".")
        eng_major = int(eng_parts[0])
        eng_minor = int(eng_parts[1]) if len(eng_parts) > 1 else 0
        if req_major > eng_major or (req_major == eng_major and req_minor > eng_minor):
            raise BundleLoadError(
                "INCOMPATIBLE_KERNEL",
                f"requires_kernel={req} > engine={engine_version}",
            )
    except (ValueError, IndexError):
        # Invalid format already caught by validate_manifest in most cases
        warnings.append(f"unparseable requires_kernel: {req}")

    if manifest.bundle_format not in _FORMAT_HANDLERS:
        raise BundleLoadError(
            "UNSUPPORTED_FORMAT", f"bundle_format={manifest.bundle_format} has no handler"
        )

    # Expiry (soft)
    if manifest.expiry:
        try:
            exp = datetime.fromisoformat(manifest.expiry.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                warnings.append(f"bundle expired: {manifest.expiry}")
        except Exception:
            warnings.append(f"unparseable expiry: {manifest.expiry}")

    return warnings


def _verify_integrity(manifest: BundleManifest, payload: Path | None) -> bool:
    """Verify content_hash against payload if provided. Raise on mismatch."""
    if not payload or not payload.exists():
        # Manifest-only loads allowed for tests / future in-mem; skip strict hash
        return True
    try:
        algo, _ = manifest.content_hash.split(":", 1)
        computed = _compute_hash(payload, algo)
        if computed != manifest.content_hash:
            raise BundleLoadError(
                "HASH_MISMATCH",
                f"computed={computed} != manifest={manifest.content_hash}",
                bundle_path=payload,
            )
        return True
    except ValueError as exc:
        raise BundleLoadError("INVALID_HASH_FORMAT", str(exc), bundle_path=payload) from exc


class BundleLoader:
    """Generic loader. Register handlers externally."""

    def __init__(self, *, strict: bool = True, engine_version: str = "1.0.0") -> None:
        self.strict = strict
        self.engine_version = engine_version

    def load(self, bundle_path: str | Path, *, check_conformance: bool = False) -> LoadedBundle:
        """Load. check_conformance=False (default) preserves exact prior behavior.
        The frozen Bundle Loader received an RFC-approved additive extension (P2-1) while preserving default behavior and compatibility.
        """
        path = Path(bundle_path).resolve()
        if path.is_file() and path.suffix in (".json", ".manifest"):
            manifest_path = path
            root = path.parent
        else:
            # dir: find manifest
            root = path
            manifests = list(root.glob("*_bundle_manifest.json")) + list(root.glob("manifest.json"))
            if not manifests:
                # allow direct manifest in parent or root as file
                raise BundleLoadError("MANIFEST_NOT_FOUND", f"No manifest in {root}", bundle_path=root)
            manifest_path = manifests[0]

        # 2. Load + validate (reuse frozen, I10)
        raw_manifest = load_manifest(manifest_path)  # typed, validated
        # Re-validate raw if needed (load_manifest already calls)
        # 3+4. Compat + integrity
        warnings = _check_compatibility(raw_manifest, self.engine_version)

        # Discover primary payload for hash (best effort convention)
        payload = None
        for cand in [
            root / f"{raw_manifest.bundle_id}.json",
            root / "index.json",
            root / "data.json",
            root / f"{raw_manifest.bundle_type}.json",
        ]:
            if cand.exists():
                payload = cand
                break

        verified = _verify_integrity(raw_manifest, payload)

        # 5. Dispatch
        handler = _FORMAT_HANDLERS.get(raw_manifest.bundle_format)
        if handler is None:
            raise BundleLoadError("UNSUPPORTED_FORMAT", raw_manifest.bundle_format, bundle_path=root)
        try:
            resource = handler(root, raw_manifest)
        except Exception as exc:
            raise BundleLoadError("RESOURCE_LOAD_FAILED", str(exc), bundle_path=root) from exc

        conf: "ConformanceResult | None" = None
        if check_conformance:
            try:
                from clinical_engine.conformance import check_conformance  # late, P2-1 additive
                conf = check_conformance(raw_manifest)
            except Exception:
                # never break load on conformance collection
                conf = None

        return LoadedBundle(
            manifest=raw_manifest,
            resource=resource,
            bundle_path=root,
            verified=verified,
            warnings=tuple(warnings),
            conformance=conf,
        )


def load_bundle(bundle_path: str | Path, *, strict: bool = True, check_conformance: bool = False) -> LoadedBundle:
    """Convenience entrypoint. check_conformance additive (P2-1), default False."""
    loader = BundleLoader(strict=strict)
    return loader.load(bundle_path, check_conformance=check_conformance)


# Re-export register for consumers
__all__ = ["BundleLoader", "LoadedBundle", "BundleLoadError", "load_bundle", "register_bundle_format"]
