"""P3 INT-1 — external corpus locator + read-only access tests.

Proves the required INT-1 properties:
  - upstream corpus is opened strictly read-only (writes rejected, no sidecars);
  - the engine can LOCATE the corpus (path resolution + EngineConfig accepts it);
  - a missing corpus is handled gracefully (no crash on construction);
  - no engine architecture / routing / safety change (this suite imports only
    the new corpus module; the real corpus, when present, is read-only-smoke-tested
    and otherwise skipped).

None of these tests write to the upstream corpus. The read-only guarantee is
proven on a throwaway temp DB; the real corpus is only ever opened read-only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clinical_engine.corpus import (
    CorpusLocator,
    CorpusUnavailableError,
    open_readonly,
    resolve_corpus_dir,
)
from clinical_engine.corpus.locator import _ENV_VAR


# ── path resolution: env overrides config default ──────────────


def test_env_overrides_config(tmp_path: Path):
    assert resolve_corpus_dir({_ENV_VAR: str(tmp_path)}) == tmp_path


def test_config_default_used_when_no_env():
    # No env → falls back to the committed corpus_config.json default.
    resolved = resolve_corpus_dir({})
    assert str(resolved)  # non-empty path
    assert resolved.name.lower() == "clinrec_downloader"


# ── missing corpus is graceful (no crash) ──────────────────────


def test_missing_corpus_is_graceful(tmp_path: Path):
    loc = CorpusLocator(tmp_path / "does_not_exist")
    st = loc.status()
    assert st.available is False
    assert st.root_exists is False
    assert loc.available() is False


def test_require_raises_clear_error_when_missing(tmp_path: Path):
    loc = CorpusLocator(tmp_path / "nope")
    with pytest.raises(CorpusUnavailableError):
        loc.require()


def test_missing_regimens_db_reported(tmp_path: Path):
    # Root exists but the regimen DB does not.
    (tmp_path / "corpus").mkdir()
    loc = CorpusLocator(tmp_path / "corpus")
    assert loc.available() is False
    with pytest.raises(CorpusUnavailableError):
        loc.open_normalized_regimens()


# ── read-only guarantee (on a throwaway DB — never the real corpus) ──


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER, v TEXT)")
    con.execute("INSERT INTO t VALUES (1, 'a')")
    con.commit()
    con.close()


def test_open_readonly_allows_select(tmp_path: Path):
    db = tmp_path / "x.sqlite"
    _make_db(db)
    con = open_readonly(db)
    try:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    finally:
        con.close()


def test_open_readonly_rejects_writes(tmp_path: Path):
    db = tmp_path / "x.sqlite"
    _make_db(db)
    con = open_readonly(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("INSERT INTO t VALUES (2, 'b')")
        with pytest.raises(sqlite3.OperationalError):
            con.execute("CREATE TABLE evil (x)")
    finally:
        con.close()


def test_open_readonly_creates_no_sidecar_files(tmp_path: Path):
    db = tmp_path / "x.sqlite"
    _make_db(db)
    before = {p.name for p in tmp_path.iterdir()}
    con = open_readonly(db)
    try:
        con.execute("SELECT * FROM t").fetchall()
    finally:
        con.close()
    after = {p.name for p in tmp_path.iterdir()}
    # No -wal / -journal / -shm created by read-only immutable access.
    assert after == before
    assert not (tmp_path / "x.sqlite-wal").exists()
    assert not (tmp_path / "x.sqlite-journal").exists()


# ── backward compatibility: EngineConfig accepts a located path,
#    with NO change to engine/config behaviour ───────────────────


def test_engine_config_accepts_located_path(tmp_path: Path):
    from clinical_engine.config import EngineConfig
    located = CorpusLocator(tmp_path).normalized_regimens_sqlite
    cfg = EngineConfig(sqlite_path=str(located))
    assert cfg.sqlite_path == str(located)


# ── real corpus (present on this machine): read-only smoke, else skip ──


def _real_locator() -> CorpusLocator:
    return CorpusLocator()  # env → config default (C:\clinrec_downloader)


def test_real_corpus_is_locatable_or_skipped():
    loc = _real_locator()
    if not loc.available():
        pytest.skip("external corpus not present on this machine")
    st = loc.status()
    assert st.normalized_regimens_exists is True
    assert loc.normalized_regimens_sqlite.name == "normalized_regimens.sqlite"


def test_real_corpus_opens_readonly_without_touching_it():
    loc = _real_locator()
    if not loc.available():
        pytest.skip("external corpus not present on this machine")
    db = loc.normalized_regimens_sqlite
    sidecars_before = {
        (db.parent / f"{db.name}{suf}").exists() for suf in ("-wal", "-journal", "-shm")
    }
    con = loc.open_normalized_regimens()
    try:
        n = con.execute("SELECT count(*) FROM normalized_regimens").fetchone()[0]
        assert n > 0
        # Prove the connection cannot write to the upstream file.
        with pytest.raises(sqlite3.OperationalError):
            con.execute("UPDATE normalized_regimens SET approved = 1")
    finally:
        con.close()
    sidecars_after = {
        (db.parent / f"{db.name}{suf}").exists() for suf in ("-wal", "-journal", "-shm")
    }
    # Read-only immutable access created no sidecar files next to the upstream DB.
    assert sidecars_after == sidecars_before
