"""Regression tests for the ANTIBIO_EXTERNAL_SITE_PACKAGES portability fix.

Root cause (fixed 2026-07-15, P5.6 owner recovery): layout.py and semantic.py
hard-coded a single workstation's site-packages path (C:\\Users\\TURPAL\\...),
which meant the literal username was baked into tracked production source and
the path only ever did anything useful on that one machine. Replaced with an
opt-in ANTIBIO_EXTERNAL_SITE_PACKAGES environment variable: absent by default
(normal imports from the active environment), validated when set, and never
silently injected.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

TARGET_FILES = [
    REPO_ROOT / "src" / "pipeline" / "extraction" / "layout.py",
    REPO_ROOT / "src" / "pipeline" / "extraction" / "semantic.py",
]

MODULES = [
    "src.pipeline.extraction.layout",
    "src.pipeline.extraction.semantic",
]

PERSONAL_PATH_RE = re.compile(r"C:\\Users\\[A-Za-z0-9_]+|/Users/[A-Za-z0-9_]+|/home/[a-z0-9_]+")


def test_no_personal_path_in_production_source():
    """Production source must contain zero hard-coded machine/username paths."""
    for f in TARGET_FILES:
        text = f.read_text(encoding="utf-8")
        assert not PERSONAL_PATH_RE.search(text), f"personal path literal found in {f}"


def _run_import(module_name: str, extra_env: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("ANTIBIO_EXTERNAL_SITE_PACKAGES", None)
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("module_name", MODULES)
def test_normal_import_without_override(module_name):
    """Absent ANTIBIO_EXTERNAL_SITE_PACKAGES: normal imports from the active
    environment must work, preserving existing behavior on every machine that
    never had the old hard-coded path."""
    result = _run_import(module_name, {})
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module_name", MODULES)
def test_invalid_override_fails_clearly(module_name):
    """A configured-but-nonexistent ANTIBIO_EXTERNAL_SITE_PACKAGES must fail
    with a clear, actionable error naming the variable — not silently no-op."""
    bogus = "Z:\\definitely-not-a-real-path\\xyz123"
    result = _run_import(module_name, {"ANTIBIO_EXTERNAL_SITE_PACKAGES": bogus})
    assert result.returncode != 0
    assert "ANTIBIO_EXTERNAL_SITE_PACKAGES" in result.stderr


@pytest.mark.parametrize("module_name", MODULES)
def test_valid_override_is_accepted(module_name, tmp_path):
    """A configured, existing ANTIBIO_EXTERNAL_SITE_PACKAGES directory must be
    accepted (added to sys.path) without error."""
    real_dir = tmp_path / "site-packages"
    real_dir.mkdir()
    result = _run_import(module_name, {"ANTIBIO_EXTERNAL_SITE_PACKAGES": str(real_dir)})
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module_name", MODULES)
def test_empty_override_behaves_as_absent(module_name):
    """An empty-string override (the .env.example placeholder default) must
    behave identically to the variable being unset."""
    result = _run_import(module_name, {"ANTIBIO_EXTERNAL_SITE_PACKAGES": ""})
    assert result.returncode == 0, result.stderr
