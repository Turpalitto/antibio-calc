from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clinical_engine.review_workbench.models import TargetType
from clinical_engine.review_workbench.service import ReviewService
from clinical_engine.review_workbench.storage import ReviewStore


ROOT = Path(__file__).resolve().parents[3]
REVIEW_DB = ROOT / "review_workbench_p56.sqlite"
CORPUS_ROOT = Path(r"C:\clinrec_downloader")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.clinical,
    pytest.mark.skipif(not REVIEW_DB.exists(), reason="P5.6 real review artifact not built"),
]


def test_real_review_populations_and_integrity():
    connection = sqlite3.connect(REVIEW_DB)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        counts = dict(connection.execute(
            "SELECT target_type,COUNT(*) FROM review_tasks GROUP BY target_type"
        ))
        assert counts["ClinicalRegimen"] == 1556
        assert counts["TherapeuticOption"] == 652
        assert counts["CorpusExclusionDecision"] == 58
        assert connection.execute(
            "SELECT COUNT(*) FROM review_tasks WHERE lifecycle_state<>'PENDING'"
        ).fetchone()[0] == 0
    finally:
        connection.close()


@pytest.mark.parametrize("target_type", [TargetType.CLINICAL_REGIMEN, TargetType.THERAPEUTIC_OPTION])
def test_real_clinical_packet_has_provenance_and_existing_pdf(target_type):
    with ReviewStore(REVIEW_DB) as store:
        task = store.list_tasks(target_type=target_type, limit=1)[0]
        packet = ReviewService(store).packet(task.task_id)
    assert packet["field_level_provenance"]
    source = packet["source_references"][0]
    assert source.get("pdf") and source.get("page")
    matches = list(CORPUS_ROOT.rglob(source["pdf"]))
    assert matches, source["pdf"]


def test_real_issue_registry_contains_all_source_issues():
    connection = sqlite3.connect(REVIEW_DB)
    try:
        source_issues = connection.execute(
            "SELECT COUNT(*) FROM clinical_data_issues WHERE detected_by<>'p5.6-dose-unit-audit-v1'"
        ).fetchone()[0]
        total = connection.execute("SELECT COUNT(*) FROM clinical_data_issues").fetchone()[0]
        assert source_issues == 4506
        assert total == 12918
    finally:
        connection.close()
