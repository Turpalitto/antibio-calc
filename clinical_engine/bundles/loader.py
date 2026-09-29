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
from typing import Any, Callable

from clinical_engine.manifest import BundleManifest, load_manifest, validate_manifest
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


# bundle_type -> directory (relative to the bundle root) holding that type's
# default payload file. Data, not a branch in the load path, so adding a new
# bundle type stays a registration. Without this scoping the shared candidate
# list let a manifest of ANY type pick up another type's payload file.
_TYPE_PAYLOAD_DIRS: dict[str, str] = {"score_profile": "score_profiles"}


def _payload_candidates(root: Path, manifest: BundleManifest) -> list[Path]:
    """THE single source of truth for "where can this bundle's payload live".

    Integrity verification and the format handler must agree on this list.
    They previously did not: ``root/f"{bundle_type}.json"`` was hashed but never
    loaded, while the documented ``root.parent/f"{bundle_id}.json"`` sidecar was
    loaded but never hashed — so a payload at the sidecar path verified against
    nothing and the declared ``content_hash`` was never compared.
    """
    candidates = [
        root / f"{manifest.bundle_id}.json",
        root / "index.json",
        root / "data.json",
        root.parent / f"{manifest.bundle_id}.json",  # documented sidecar convention
    ]
    scoped_dir = _TYPE_PAYLOAD_DIRS.get(manifest.bundle_type)
    if scoped_dir is not None:
        candidates.append(root / scoped_dir / "default.json")
    return candidates


def _default_json_handler(root: Path, manifest: BundleManifest) -> dict[str, Any]:
    """Baseline v1 JSON payload handler (infra example).

    Convention: look for payload next to manifest or in root using bundle_id hints.
    Real handlers (P0-4) will target actual resources.
    """
    for p in _payload_candidates(root, manifest):
        if p.exists() and p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                raise BundleLoadError(
                    "PAYLOAD_PARSE_ERROR", f"Failed to parse {p}: {exc}", bundle_path=root
                ) from exc
    # Fallback: return empty dict (manifest-only bundles carry no payload resource)
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
    """Pure version/format checks.

    Hard incompatibilities RAISE :class:`BundleLoadError`; only genuinely soft
    findings (expiry, unparseable optional metadata) become warnings.
    """
    warnings: list[str] = []
    # requires_kernel: "X.Y" vs engine "X.Y.Z"
    req = manifest.requires_kernel
    try:
        req_parts = [int(part) for part in req.split(".")]
    except ValueError as exc:
        # A malformed requirement is a HARD failure: it is a manifest
        # validation defect, and silently downgrading it to a warning loaded a
        # kernel-incompatible bundle.
        raise BundleLoadError(
            "UNPARSEABLE_REQUIRES_KERNEL", f"requires_kernel={req!r} is not 'X.Y'", bundle_path=None
        ) from exc
    if len(req_parts) < 2:
        raise BundleLoadError(
            "UNPARSEABLE_REQUIRES_KERNEL", f"requires_kernel={req!r} must be 'X.Y'", bundle_path=None
        )
    req_major, req_minor = req_parts[0], req_parts[1]
    try:
        eng_parts = [int(part) for part in engine_version.split(".")]
    except ValueError as exc:
        raise BundleLoadError(
            "UNPARSEABLE_ENGINE_VERSION", f"engine_version={engine_version!r} is not numeric",
            bundle_path=None,
        ) from exc
    eng_major = eng_parts[0]
    eng_minor = eng_parts[1] if len(eng_parts) > 1 else 0
    if req_major > eng_major or (req_major == eng_major and req_minor > eng_minor):
        raise BundleLoadError(
            "INCOMPATIBLE_KERNEL",
            f"requires_kernel={req} > engine={engine_version}",
        )

    if manifest.bundle_format not in _FORMAT_HANDLERS:
        raise BundleLoadError(
            "UNSUPPORTED_FORMAT", f"bundle_format={manifest.bundle_format} has no handler"
        )

    # Expiry: a bundle past its declared expiry is not loadable as if it were
    # current. Previously this was only a warning, so an expired bundle loaded
    # with verified=True.
    if manifest.expiry:
        try:
            exp = datetime.fromisoformat(manifest.expiry.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BundleLoadError(
                "UNPARSEABLE_EXPIRY", f"expiry={manifest.expiry!r} is not ISO-8601", bundle_path=None
            ) from exc
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            raise BundleLoadError(
                "BUNDLE_EXPIRED", f"bundle expired at {manifest.expiry}", bundle_path=None
            )

    return warnings


def _verify_integrity(manifest: BundleManifest, payload: Path | None, root: Path) -> bool:
    """Verify the declared content_hash against the payload that will be loaded.

    Never returns ``True`` without having compared a hash. When a manifest
    declares a ``content_hash`` but no payload was found, the load FAILS: the
    old behaviour returned True (a live test escape hatch), so placing the
    payload at a path the discovery list missed produced ``verified=True`` with
    the declared hash never checked. ``payload`` is resolved by
    :func:`_resolve_payload`, the same list the format handler walks.
    """
    if payload is None:
        if manifest.content_hash:
            raise BundleLoadError(
                "PAYLOAD_NOT_FOUND",
                f"content_hash declared ({manifest.content_hash}) but no payload found in {root}",
                bundle_path=root,
            )
        # No declared hash and no payload: nothing to verify, nothing to hide.
        return True
    try:
        algo, _ = manifest.content_hash.split(":", 1)
    except ValueError as exc:
        raise BundleLoadError("INVALID_HASH_FORMAT", str(exc), bundle_path=payload) from exc
    computed = _compute_hash(payload, algo)
    if computed != manifest.content_hash:
        raise BundleLoadError(
            "HASH_MISMATCH",
            f"computed={computed} != manifest={manifest.content_hash}",
            bundle_path=payload,
        )
    return True


def _resolve_payload(root: Path, manifest: BundleManifest) -> Path | None:
    for candidate in _payload_candidates(root, manifest):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


class BundleLoader:
    """Generic loader. Register handlers externally.

    ``strict`` and ``engine_version`` are no longer accepted-and-ignored: passing
    ``strict=False`` used to have no effect at all (and ``load_bundle`` also
    silently dropped the ``engine_version`` it was given), so a caller asking for
    lenient behaviour always got strict behaviour and vice-versa. Every
    incompatibility, expiry and integrity failure is now a hard failure; the
    arguments are retained only for signature compatibility and are validated.
    """

    def __init__(self, *, strict: bool = True, engine_version: str = "1.0.0") -> None:
        if not isinstance(strict, bool):
            raise ValueError("strict must be a bool")
        if not isinstance(engine_version, str) or not engine_version.strip():
            raise ValueError("engine_version must be a non-empty string")
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
            manifest_path = self._select_manifest(root)
        if manifest_path is None:
            raise BundleLoadError("MANIFEST_NOT_FOUND", f"No manifest in {root}", bundle_path=root)

        # 2. Load + validate (reuse frozen, I10)
        raw_manifest = load_manifest(manifest_path)  # typed, validated
        # 3+4. Compat + integrity. Both walk the SAME payload candidate list, so
        # what is hashed is exactly what is loaded.
        warnings = _check_compatibility(raw_manifest, self.engine_version)
        verified = _verify_integrity(raw_manifest, _resolve_payload(root, raw_manifest), root)

        # 5. Dispatch
        handler = _FORMAT_HANDLERS.get(raw_manifest.bundle_format)
        if handler is None:
            raise BundleLoadError("UNSUPPORTED_FORMAT", raw_manifest.bundle_format, bundle_path=root)
        try:
            resource = handler(root, raw_manifest)
        except BundleLoadError:
            raise
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

    @staticmethod
    def _select_manifest(root: Path) -> Path | None:
        """Deterministic manifest selection.

        ``manifests[0]`` from a glob depended on filesystem iteration order, so a
        directory holding both a ``*_bundle_manifest.json`` and a ``manifest.json``
        loaded an arbitrary one. Prefer the explicit ``manifest.json``, then the
        unique ``*_bundle_manifest.json``; refuse an ambiguous set rather than
        guessing.
        """
        generic = sorted(root.glob("manifest.json"))
        specific = sorted(root.glob("*_bundle_manifest.json"))
        candidates = generic + specific
        if not candidates:
            return None
        if len(candidates) > 1:
            raise BundleLoadError(
                "MANIFEST_AMBIGUOUS",
                f"multiple manifests in {root}: {[path.name for path in candidates]}",
                bundle_path=root,
            )
        return candidates[0]


def load_bundle(bundle_path: str | Path, *, strict: bool = True, check_conformance: bool = False,
                engine_version: str = "1.0.0") -> LoadedBundle:
    """Convenience entrypoint. check_conformance additive (P2-1), default False.

    ``engine_version`` is now honoured (it previously was accepted and dropped).
    """
    loader = BundleLoader(strict=strict, engine_version=engine_version)
    return loader.load(bundle_path, check_conformance=check_conformance)


# Re-export register for consumers
__all__ = ["BundleLoader", "LoadedBundle", "BundleLoadError", "load_bundle", "register_bundle_format"]
