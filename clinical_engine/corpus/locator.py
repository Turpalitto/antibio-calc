"""Read-only locator for the external Clinical Guideline corpus (P3 INT-1).

The corpus (guideline PDFs, ``metadata.sqlite``, ``normalized_regimens.sqlite``)
is a large research asset stored OUTSIDE git at ``C:\\clinrec_downloader``. This
module lets the engine and tooling *reference* it read-only. It never writes,
copies, moves, or modifies the upstream corpus, and it adds no medical knowledge
to the repository — only path resolution and a read-only SQLite opener.

Path resolution (first match wins):
  1. env ``ANTIBIO_CORPUS_DIR``
  2. ``corpus_config.json`` ("corpus_dir")  — committed default
  3. built-in ``_FALLBACK_CORPUS_DIR``

Read-only guarantee: :func:`open_readonly` opens SQLite via URI
``mode=ro&immutable=1``. ``immutable=1`` tells SQLite the file cannot change, so
it performs NO locking and creates NO ``-wal`` / ``-journal`` / ``-shm``
sidecars — the upstream file (and its directory) is never touched. Writes on the
returned connection raise ``sqlite3.OperationalError``.

Scope note (INT-1): this module only *locates* the corpus and opens it
read-only. It does not change the engine, the pipeline, routing, or the safety
stages, and it does not wire the corpus into ``SQLiteReader`` — that is a later,
separately-approved increment.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "corpus_config.json"
_FALLBACK_CORPUS_DIR = r"C:\clinrec_downloader"
_ENV_VAR = "ANTIBIO_CORPUS_DIR"

_NORMALIZED_REGIMENS = "normalized_regimens.sqlite"
_METADATA = "metadata.sqlite"
_DEFAULT_PDF_DIRS = ("downloads_active", "archive_review", "archive_no_antibiotics")


class CorpusUnavailableError(RuntimeError):
    """Raised when the external corpus (or a required artifact) is not present.

    Callers that must degrade gracefully should check :meth:`CorpusLocator.available`
    instead of catching this.
    """


def _config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_corpus_dir(env: dict[str, str] | None = None) -> Path:
    """Resolve the corpus root: env override → config default → fallback.

    Pure path resolution — does not check existence (see
    :meth:`CorpusLocator.available`).
    """
    env = os.environ if env is None else env
    val = env.get(_ENV_VAR)
    if val and val.strip():
        return Path(val.strip())
    cfg = _config().get("corpus_dir")
    if cfg and str(cfg).strip():
        return Path(str(cfg).strip())
    return Path(_FALLBACK_CORPUS_DIR)


def open_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open an SQLite file strictly read-only (no writes, no sidecar files).

    Raises ``sqlite3.OperationalError`` if the file does not exist or cannot be
    opened. The returned connection rejects any write (INSERT/UPDATE/CREATE/...).
    """
    p = Path(db_path).resolve()
    uri = p.as_uri() + "?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


@dataclass(frozen=True)
class CorpusStatus:
    root: Path
    root_exists: bool
    normalized_regimens_exists: bool
    metadata_exists: bool
    pdf_dirs_present: tuple[str, ...]

    @property
    def available(self) -> bool:
        # "available" for engine consumption = root + the regimen DB the engine reads.
        return self.root_exists and self.normalized_regimens_exists


class CorpusLocator:
    """Read-only reference to the external corpus. Construction never raises and
    never touches the filesystem beyond ``.exists()`` checks."""

    def __init__(self, corpus_dir: str | Path | None = None,
                 env: dict[str, str] | None = None) -> None:
        self._root = Path(corpus_dir) if corpus_dir is not None else resolve_corpus_dir(env)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def normalized_regimens_sqlite(self) -> Path:
        return self._root / _NORMALIZED_REGIMENS

    @property
    def metadata_sqlite(self) -> Path:
        return self._root / _METADATA

    def pdf_dirs(self) -> tuple[Path, ...]:
        names = _config().get("expected_artifacts", {}).get("pdf_dirs", _DEFAULT_PDF_DIRS)
        return tuple(self._root / n for n in names)

    def status(self) -> CorpusStatus:
        present = tuple(d.name for d in self.pdf_dirs() if d.is_dir())
        return CorpusStatus(
            root=self._root,
            root_exists=self._root.is_dir(),
            normalized_regimens_exists=self.normalized_regimens_sqlite.is_file(),
            metadata_exists=self.metadata_sqlite.is_file(),
            pdf_dirs_present=present,
        )

    def available(self) -> bool:
        return self.status().available

    def require(self) -> None:
        st = self.status()
        if st.available:
            return
        if not st.root_exists:
            raise CorpusUnavailableError(
                f"Corpus directory not found: {self._root}. "
                f"Set {_ENV_VAR} or corpus_config.json to the corpus location."
            )
        raise CorpusUnavailableError(
            f"Corpus at {self._root} is missing {_NORMALIZED_REGIMENS} "
            "(the regimen database the engine consumes)."
        )

    def open_normalized_regimens(self) -> sqlite3.Connection:
        """Open the upstream normalized_regimens DB read-only. Raises
        CorpusUnavailableError if absent."""
        if not self.normalized_regimens_sqlite.is_file():
            self.require()
        return open_readonly(self.normalized_regimens_sqlite)

    def open_metadata(self) -> sqlite3.Connection:
        """Open the upstream metadata DB read-only. Raises CorpusUnavailableError
        if absent."""
        if not self.metadata_sqlite.is_file():
            raise CorpusUnavailableError(
                f"metadata.sqlite not found under {self._root}"
            )
        return open_readonly(self.metadata_sqlite)
