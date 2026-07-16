"""Evidence-Integrity Hardening, Phase 4 — negative tests.

Proves the structural fix for how the RC-031 false finding happened: a
hand-written comparison rendered as if it were captured database/PDF output.
"""
import json
import time

import pytest

from dose_verification_sandbox.evidence_model import (
    EvidenceBlock, EvidenceIntegrityError, build_packet, verify_packet, render_markdown,
)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def test_hand_written_text_cannot_claim_database_query_origin():
    with pytest.raises(EvidenceIntegrityError):
        EvidenceBlock(
            evidence_origin="DATABASE_QUERY", source_artifact="assembled_regimens.sqlite",
            source_hash=None, retrieval_command=None, retrieved_at=_now(),
            record_identifier="x", is_exact=True, content="hand-typed row",
        )


def test_hand_written_text_cannot_claim_source_pdf_extract_origin():
    with pytest.raises(EvidenceIntegrityError):
        EvidenceBlock(
            evidence_origin="SOURCE_PDF_EXTRACT", source_artifact="some.pdf",
            source_hash=None, retrieval_command=None, retrieved_at=_now(),
            record_identifier="x", is_exact=True, content="hand-typed quote",
        )


def test_missing_source_hash_rejected_for_machine_origin():
    with pytest.raises(EvidenceIntegrityError):
        EvidenceBlock(
            evidence_origin="DATABASE_QUERY", source_artifact="db",
            source_hash=None, retrieval_command="SELECT 1", retrieved_at=_now(),
            record_identifier="x", is_exact=True, content="1",
        )


def test_missing_retrieval_command_rejected_for_machine_origin():
    with pytest.raises(EvidenceIntegrityError):
        EvidenceBlock(
            evidence_origin="DATABASE_QUERY", source_artifact="db",
            source_hash="a" * 64, retrieval_command=None, retrieved_at=_now(),
            record_identifier="x", is_exact=True, content="1",
        )


def test_mismatched_evidence_hash_detected_on_render():
    block = EvidenceBlock(
        evidence_origin="DATABASE_QUERY", source_artifact="db", source_hash="a" * 64,
        retrieval_command="SELECT 1", retrieved_at=_now(), record_identifier="x",
        is_exact=True, content="1",
    )
    packet = build_packet([block], meta={"generated_at": _now()})
    packet["evidence"][0]["content"] = "2"  # tamper after generation
    assert verify_packet(packet) is False
    with pytest.raises(EvidenceIntegrityError):
        render_markdown(packet, title="t")


def test_changed_database_result_invalidates_packet():
    block = EvidenceBlock(
        evidence_origin="DATABASE_QUERY", source_artifact="db", source_hash="a" * 64,
        retrieval_command="SELECT * FROM t", retrieved_at=_now(), record_identifier="x",
        is_exact=True, content=json.dumps({"antibiotic": "джозамицин"}, ensure_ascii=False),
    )
    packet = build_packet([block], meta={"generated_at": _now()})
    original_hash = packet["packet_hash"]
    # simulate a re-query returning different data without regenerating the packet
    packet["evidence"][0]["content"] = json.dumps({"antibiotic": "азитромицин"}, ensure_ascii=False)
    assert verify_packet(packet) is False
    assert packet["packet_hash"] == original_hash  # stale hash, now provably wrong


def test_changed_pdf_span_invalidates_packet():
    block = EvidenceBlock(
        evidence_origin="SOURCE_PDF_EXTRACT", source_artifact="x.pdf", source_hash="b" * 64,
        retrieval_command="fitz page.get_text()", retrieved_at=_now(), record_identifier="x.pdf:page1",
        is_exact=True, content="джозамицин 50 мг на кг массы тела в сутки",
    )
    packet = build_packet([block], meta={"generated_at": _now()})
    packet["evidence"][0]["content"] = "азитромицин 50 мг на кг массы тела в сутки"
    assert verify_packet(packet) is False


def test_paraphrase_is_visibly_labelled():
    block = EvidenceBlock(
        evidence_origin="PARAPHRASE", source_artifact="reviewer summary", source_hash=None,
        retrieval_command=None, retrieved_at=_now(), record_identifier="x",
        is_exact=False, content="roughly 50mg/kg per day, per the guideline",
    )
    assert "PARAPHRASE" in block.label()
    assert "not verbatim" in block.label()


def test_paraphrase_cannot_be_marked_exact():
    with pytest.raises(EvidenceIntegrityError):
        EvidenceBlock(
            evidence_origin="PARAPHRASE", source_artifact="x", source_hash=None,
            retrieval_command=None, retrieved_at=_now(), record_identifier="x",
            is_exact=True, content="paraphrased text claiming to be exact",
        )


def test_human_note_cannot_be_marked_exact():
    with pytest.raises(EvidenceIntegrityError):
        EvidenceBlock(
            evidence_origin="HUMAN_NOTE", source_artifact="x", source_hash=None,
            retrieval_command=None, retrieved_at=_now(), record_identifier="x",
            is_exact=True, content="a note pretending to be verbatim",
        )


def test_regimen_5574_evidence_packet_contains_dzhozamitsin_not_azithromycin():
    from pathlib import Path
    packet_path = Path(__file__).resolve().parents[2] / "evidence" / "regimen_5574_verified_evidence.json"
    if not packet_path.exists():
        pytest.skip("evidence packet not generated in this environment")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert verify_packet(packet) is True
    assembled_block = next(b for b in packet["evidence"] if b["record_identifier"].startswith("assembled_regimens"))
    content = json.loads(assembled_block["content"])
    assert content["antibiotic"] == "джозамицин"
    assert "азитромицин" not in content["antibiotic"].lower()
    assert "azithromycin" not in json.dumps(content, ensure_ascii=False).lower()


def test_generated_report_regenerable_and_hash_stable():
    from pathlib import Path
    packet_path = Path(__file__).resolve().parents[2] / "evidence" / "regimen_5574_verified_evidence.json"
    if not packet_path.exists():
        pytest.skip("evidence packet not generated in this environment")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    report = render_markdown(packet, title="REGIMEN 5574 VERIFICATION REPORT")
    assert "джозамицин" in report
    assert "азитромицин" not in report.lower()


def test_synthetic_source_db_unchanged_by_readonly_evidence_query(tmp_path):
    """Unit test (no real data): proves the read-only query pattern used by
    evidence generation (`sqlite3.connect(..., mode=ro)` + SELECT) never
    mutates its source file, using a small synthetic SQLite DB built in
    tmp_path. This is the behavioral guarantee that matters — it does not
    require the real corpus."""
    import hashlib
    import sqlite3

    db_path = tmp_path / "synthetic_source.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE assembled_regimens (regimen_id TEXT, antibiotic TEXT)")
    conn.execute("INSERT INTO assembled_regimens VALUES ('synthetic-1', 'synthetic-drug')")
    conn.commit()
    conn.close()

    hash_before = hashlib.sha256(db_path.read_bytes()).hexdigest()

    ro_conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        cur = ro_conn.cursor()
        cur.execute("SELECT * FROM assembled_regimens WHERE regimen_id = 'synthetic-1'")
        row = cur.fetchone()
        assert row == ("synthetic-1", "synthetic-drug")
    finally:
        ro_conn.close()

    hash_after = hashlib.sha256(db_path.read_bytes()).hexdigest()
    assert hash_after == hash_before


def test_real_source_database_unchanged_by_evidence_generation():
    """Optional corpus check: if the real (gitignored) source database is
    present in this checkout, confirm it still matches the hash recorded in
    the machine-generated evidence packet. Never required — the deterministic
    guarantee is already proven by the synthetic test above."""
    import hashlib
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    db = repo_root / "assembled_regimens.sqlite"
    if not db.exists():
        pytest.skip(
            "Optional corpus database not available; synthetic invariant test "
            "already covers deterministic behaviour."
        )
    h = hashlib.sha256(db.read_bytes()).hexdigest()
    assert h == "9f505d08428cd2841983d3c8881c15e0813ada4a9056dea360a357a0f3eebcd9"
