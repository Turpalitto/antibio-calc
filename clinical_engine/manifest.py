"""BundleManifest loader and validator for P0-1.

Implements exactly the frozen BundleManifest Specification from RFC P0-1.

No architecture changes, no new fields.

Per I10 Forward Compatibility: unknown optional fields are ignored (not rejected).

Uses simple structural validation (no external jsonschema dep for P0-1 minimality).
Full JSON Schema validation can be layered later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True, slots=True)
class BundleManifest:
    """Typed representation of a BundleManifest.

    All fields from the approved RFC P0-1.
    Unknown fields from raw dict are dropped per I10 (not stored).
    """

    schema_version: str
    version: str
    requires_kernel: str
    bundle_format: str
    content_hash: str
    bundle_id: str
    bundle_type: str
    curation_status: Optional[str] = None
    generated_by: Optional[str] = None
    source_refs: List[str] = field(default_factory=list)
    jurisdiction: Optional[str] = None
    specialty: Optional[str] = None
    signatures: List[Dict[str, Any]] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    supersedes: List[str] = field(default_factory=list)
    expiry: Optional[str] = None
    freshness_policy: Optional[Dict[str, Any]] = None
    stats: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


def _load_schema() -> Dict[str, Any]:
    """Load the frozen JSON Schema."""
    schema_path = Path(__file__).parent / "resources" / "bundle_manifest.schema.json"
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


def validate_manifest(manifest: Dict[str, Any]) -> None:
    """Validate a raw manifest dict against the P0-1 schema.

    Raises ValueError with clear message on failure.
    Per I10: extra unknown fields are tolerated (not validated as error here;
    the kernel must ignore them).
    This is a structural/type validator. For stricter JSON Schema enforcement
    (including patterns/enums), load the .schema.json with jsonschema library
    in consuming code.
    """
    schema = _load_schema()
    props = schema.get("properties", {})
    required = schema.get("required", [])

    # Required fields
    for field_name in required:
        if field_name not in manifest:
            raise ValueError(f"Missing required field: {field_name}")

    # Basic type and format validation for known fields
    for key, value in manifest.items():
        if key not in props:
            # I10: ignore unknown optional fields
            continue

        prop = props[key]
        expected_type = prop.get("type")

        if expected_type == "string":
            if not isinstance(value, str):
                raise ValueError(f"Field {key} must be string, got {type(value)}")
            if "pattern" in prop and not _matches_pattern(value, prop["pattern"]):
                raise ValueError(f"Field {key} does not match pattern {prop['pattern']}")
            if "enum" in prop and value not in prop["enum"]:
                # For bundle_type and similar, tolerate unknown per I10
                if key != "bundle_type":
                    raise ValueError(f"Field {key} must be one of {prop['enum']}")

        elif expected_type == "array":
            if not isinstance(value, list):
                raise ValueError(f"Field {key} must be array, got {type(value)}")
            if "items" in prop and prop["items"].get("type") == "string":
                for item in value:
                    if not isinstance(item, str):
                        raise ValueError(f"Field {key} items must be strings")

        elif expected_type in (["string", "null"], "object", ["object", "null"]):
            if expected_type in (["string", "null"], ["object", "null"]):
                if value is not None and not isinstance(value, (str if "string" in str(expected_type) else dict)):
                    # loose for nullables
                    if "string" in str(expected_type) and not isinstance(value, (str, type(None))):
                        raise ValueError(f"Field {key} must be string or null")
                    if "object" in str(expected_type) and not isinstance(value, (dict, type(None))):
                        raise ValueError(f"Field {key} must be object or null")
            elif not isinstance(value, dict):
                raise ValueError(f"Field {key} must be object, got {type(value)}")

    # Specific format checks (per RFC: algorithm identifiers)
    if "content_hash" in manifest:
        ch = manifest["content_hash"]
        if ":" not in ch or not ch.split(":", 1)[1]:
            raise ValueError("content_hash must be in 'algorithm:hex' format")

    if "signatures" in manifest and manifest["signatures"]:
        for sig in manifest["signatures"]:
            if not isinstance(sig, dict) or "algorithm" not in sig or "value" not in sig:
                raise ValueError("Each signature must have 'algorithm' and 'value'")
            if not isinstance(sig["algorithm"], str):
                raise ValueError("signature algorithm must be string")

    # bundle_type: do not hard-reject unknown for I10 forward compat.
    # Schema lists current known, but kernel/loader can decide strictness.


def _matches_pattern(value: str, pattern: str) -> bool:
    """Minimal pattern matcher for semver-like (avoids re dep)."""
    import re
    try:
        return bool(re.match(pattern, value))
    except Exception:
        return False


def load_manifest(data: Dict[str, Any] | str | Path) -> BundleManifest:
    """Load and validate a BundleManifest.

    Accepts dict, JSON string, or file path.
    Returns typed BundleManifest (unknown fields dropped per I10).
    """
    if isinstance(data, (str, Path)):
        if isinstance(data, Path) or (isinstance(data, str) and data.endswith((".json", ".manifest"))):
            with open(data, encoding="utf-8") as f:
                raw = json.load(f)
        else:
            raw = json.loads(data)
    else:
        raw = data

    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a dict")

    validate_manifest(raw)

    # Build only known fields (drop unknown per I10)
    known = {
        "schema_version": raw.get("schema_version"),
        "version": raw.get("version"),
        "requires_kernel": raw.get("requires_kernel"),
        "bundle_format": raw.get("bundle_format"),
        "content_hash": raw.get("content_hash"),
        "bundle_id": raw.get("bundle_id"),
        "bundle_type": raw.get("bundle_type"),
        "curation_status": raw.get("curation_status"),
        "generated_by": raw.get("generated_by"),
        "source_refs": raw.get("source_refs", []),
        "jurisdiction": raw.get("jurisdiction"),
        "specialty": raw.get("specialty"),
        "signatures": raw.get("signatures", []),
        "depends_on": raw.get("depends_on", []),
        "supersedes": raw.get("supersedes", []),
        "expiry": raw.get("expiry"),
        "freshness_policy": raw.get("freshness_policy"),
        "stats": raw.get("stats"),
        "notes": raw.get("notes"),
    }

    return BundleManifest(**{k: v for k, v in known.items() if v is not None or k in ["source_refs", "signatures", "depends_on", "supersedes"]})


# Example usage in docs / tests:
# manifest = load_manifest({"schema_version": "1.0.0", "version": "1.0.0", ...})
