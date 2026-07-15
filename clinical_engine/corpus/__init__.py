"""External Clinical Guideline corpus integration (read-only reference layer).

INT-1: locate the corpus and open it read-only. No engine/pipeline/safety
change; no medical knowledge stored in the repo.
"""

from clinical_engine.corpus.locator import (
    CorpusLocator,
    CorpusStatus,
    CorpusUnavailableError,
    open_readonly,
    resolve_corpus_dir,
)
from clinical_engine.corpus.provenance import (
    MetadataNotFound,
    PdfNotFound,
    ProvenanceError,
    ProvenanceRecord,
    ProvenanceResolver,
    RegimenNotFound,
    ReviewInfoMissing,
    ShaMismatch,
)

__all__ = [
    "CorpusLocator",
    "CorpusStatus",
    "CorpusUnavailableError",
    "open_readonly",
    "resolve_corpus_dir",
    "ProvenanceResolver",
    "ProvenanceRecord",
    "ProvenanceError",
    "RegimenNotFound",
    "MetadataNotFound",
    "PdfNotFound",
    "ShaMismatch",
    "ReviewInfoMissing",
]
