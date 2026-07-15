"""Milestone 1: config.py — EngineConfig + Profiles."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from clinical_engine.config import EngineConfig, Profiles
from clinical_engine.models import ValidationPolicy


class TestEngineConfig:
    def test_defaults(self) -> None:
        cfg = EngineConfig(sqlite_path="C:/clinrec_downloader/metadata.sqlite")
        # Audit fix M3: default resource paths are package-anchored absolute
        # paths (not CWD-relative), so the engine works from any working dir.
        assert cfg.drug_reference_path.replace("\\", "/").endswith("db/index.json")
        assert Path(cfg.drug_reference_path).is_absolute()
        assert cfg.diagnosis_index_path.replace("\\", "/").endswith(
            "clinical_engine/resources/diagnosis_index.json"
        )
        assert cfg.clinical_constants_path.replace("\\", "/").endswith(
            "clinical_engine/resources/clinical_constants.json"
        )
        assert cfg.score_profile == "default"
        assert cfg.validation_policy is ValidationPolicy.STRICT
        assert cfg.debug is False
        assert cfg.cache_readers is True
        assert cfg.strict_mode is True  # Milestone 13: safe by default

    def test_frozen(self) -> None:
        cfg = EngineConfig(sqlite_path="x.sqlite")
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(cfg, "debug", True)


class TestProfiles:
    def test_production_is_strict(self) -> None:
        cfg = Profiles.production("x.sqlite")
        assert cfg.validation_policy is ValidationPolicy.STRICT
        assert cfg.debug is False
        assert cfg.strict_mode is True  # production guards uncurated index

    def test_non_production_profiles_relax_strict_mode(self) -> None:
        for factory in (Profiles.research, Profiles.development, Profiles.audit):
            assert factory("x.sqlite").strict_mode is False

    def test_research_is_allow_review(self) -> None:
        cfg = Profiles.research("x.sqlite")
        assert cfg.validation_policy is ValidationPolicy.ALLOW_REVIEW

    def test_development_is_debug(self) -> None:
        cfg = Profiles.development("x.sqlite")
        assert cfg.validation_policy is ValidationPolicy.DEBUG
        assert cfg.debug is True

    def test_audit_is_audit_policy(self) -> None:
        cfg = Profiles.audit("x.sqlite")
        assert cfg.validation_policy is ValidationPolicy.AUDIT

    def test_all_profiles_carry_sqlite_path(self) -> None:
        for factory in (Profiles.production, Profiles.research, Profiles.development, Profiles.audit):
            cfg = factory("shared_path.sqlite")
            assert cfg.sqlite_path == "shared_path.sqlite"
