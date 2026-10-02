"""Corpus-root resolution in the pipeline layer (src/pipeline/config.py).

Regression guard for the Windows-layout path assumption: ``BASE_DIR`` used to
be ``Path(__file__).parents[3] / "clinrec_downloader"``, which on any non-Windows
checkout silently produced a non-existent path and changed meaning whenever the
file changed depth (the L-31 defect class).

The contract under test is the resolution order — env ``ANTIBIO_CORPUS_DIR`` →
committed ``clinical_engine/corpus/corpus_config.json`` → repo-root sibling — and
that it agrees with the sanctioned engine locator, so the two layers cannot
disagree about where the corpus is.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import (
    _CORPUS_CONFIG_REL,
    _CORPUS_DIR_NAME,
    _CORPUS_ENV_VAR,
    _configured_corpus_dir,
    repo_root,
    resolve_corpus_dir,
)


# ── env override wins ──────────────────────────────────────────


def test_env_override_is_used(tmp_path: Path):
    assert resolve_corpus_dir({_CORPUS_ENV_VAR: str(tmp_path)}) == tmp_path


def test_blank_env_is_ignored_and_falls_through():
    # A set-but-empty variable must not resolve the corpus to "".
    for blank in ("", "   "):
        resolved = resolve_corpus_dir({_CORPUS_ENV_VAR: blank})
        assert str(resolved).strip()
        assert resolved == Path(_configured_corpus_dir() or resolved)


def test_env_value_is_stripped():
    assert resolve_corpus_dir({_CORPUS_ENV_VAR: "  /tmp/spaced  "}) == Path("/tmp/spaced")


# ── committed default ──────────────────────────────────────────


def test_repo_root_is_found_by_marker():
    root = repo_root()
    # Marker-based: the root must actually be a checkout root.
    assert (root / "pyproject.toml").is_file()
    assert (root / "src").is_dir()


def test_default_matches_committed_corpus_config():
    configured = _configured_corpus_dir()
    assert configured, "corpus_config.json must define corpus_dir"
    # No env → the committed default is what the pipeline uses.
    assert resolve_corpus_dir({}) == Path(configured)


def test_corpus_config_is_read_from_the_repository_root():
    # Same file the engine locator reads — one source of truth for the default.
    path = repo_root() / _CORPUS_CONFIG_REL
    assert path.is_file()
    assert str(json.loads(path.read_text(encoding="utf-8"))["corpus_dir"]).strip() == _configured_corpus_dir()


# ── compatibility with the engine locator ──────────────────────


def test_resolution_agrees_with_engine_locator():
    from clinical_engine.corpus.locator import resolve_corpus_dir as engine_resolve

    assert Path(str(resolve_corpus_dir({}))) == Path(str(engine_resolve({})))


def test_engine_config_default_and_pipeline_agree_on_the_tail():
    """Separator-agnostic: the committed default is a Windows path, which native
    POSIX ``Path`` cannot split, so compare the final component only."""
    resolved = str(resolve_corpus_dir({})).replace("\\", "/").rstrip("/")
    assert resolved.rsplit("/", 1)[-1].lower() == _CORPUS_DIR_NAME


# ── depth independence (the actual defect) ─────────────────────


def test_resolution_finds_a_nested_root_by_marker(tmp_path: Path):
    """Depth-independence, proven for real rather than skipped.

    Build a synthetic checkout (``pyproject.toml`` + committed corpus config),
    drop a copy of this module several levels deep inside it, and import that
    copy. Marker-based resolution must reach the synthetic root and pick up its
    committed default — which the old depth-based expression could not do.
    """
    import importlib.util

    root = tmp_path / "fakerepo"
    (root / "clinical_engine" / "corpus").mkdir(parents=True)
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    (root / "clinical_engine" / "corpus" / "corpus_config.json").write_text(
        json.dumps({"corpus_dir": str(tmp_path / "corpus_elsewhere")}), encoding="utf-8"
    )

    deep = root / "src" / "pipeline" / "nested" / "deeper"
    deep.mkdir(parents=True)
    copy = deep / "config_copy.py"
    copy.write_text(
        Path(__file__).resolve().parents[1].joinpath("pipeline", "config.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    spec = importlib.util.spec_from_file_location("config_copy", copy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # The synthetic root is found from five levels down, and its committed
    # default (not a depth-derived guess) is what resolves.
    assert module.repo_root() == root
    assert module.resolve_corpus_dir({}) == tmp_path / "corpus_elsewhere"
    assert module.BASE_DIR == tmp_path / "corpus_elsewhere"
