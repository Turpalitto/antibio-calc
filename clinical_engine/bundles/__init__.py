"""Bundle infrastructure (P0-3).

Pure generic loader. No medical, no reader, no provider logic.
New formats = register new handler only.
"""

from .loader import (
    BundleLoadError,
    BundleLoader,
    LoadedBundle,
    load_bundle,
    register_bundle_format,
)
from ..conformance import (  # P2-1 additive
    ConformanceIssue,
    ConformanceResult,
    ConformanceValidator,
    check_conformance,
)

__all__ = [
    "BundleLoadError",
    "BundleLoader",
    "LoadedBundle",
    "load_bundle",
    "register_bundle_format",
    "ConformanceIssue",
    "ConformanceResult",
    "ConformanceValidator",
    "check_conformance",
]
