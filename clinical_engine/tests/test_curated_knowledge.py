"""P3 INT-4 — unified curated knowledge + review-required gate tests.

Covers: deterministic unification build, CuratedKnowledge query semantics
(approved vs explicit ReviewRequired — never silent fallback), the CuratedEngine
gate (unapproved -> review-required; approved -> passthrough with provenance),
the 5 cross-layer validation failures, and backward compatibility (the plain
Engine is not modified).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from clinical_engine.curated import (
    ApprovedChain,
    CuratedEngine,
    CuratedKnowledge,
    ReviewRequired,
)
from clinical_engine.tools import build_curated_knowledge, validate_curated_knowledge


# ── fixtures ───────────────────────────────────────────────────


def _dx_ledger(decisions):
    return {"decisions": decisions}


def _dx_decision(dx, gid, **over):
    d = {"conflict_id": "c", "diagnosis": dx, "severity": "CRITICAL",
         "guideline_options": [{"guideline_id": gid, "icd10": ["X"], "title": "t"},
                               {"guideline_id": "other", "icd10": ["Y"], "title": "t2"}],
         "decision": "select_primary", "chosen_guideline_id": gid,
         "decided_by": "Тестов Т.Т., ЛОР", "decided_at": "2026-07-11T00:00:00Z",
         "rationale": "verified"}
    d.update(over)
    return d


def _curated_regimens(regimens):
    return {"approved_regimens": regimens}


def _reg(rid, gid, **over):
    r = {"regimen_id": rid, "guideline_id": gid, "kr_code": "494",
         "pdf_sha256": "a" * 64, "pdf_sha256_verified": True,
         "pdf_path": "/corpus/g.pdf", "page_number": "27",
         "decided_by": "Тестов Т.Т., ЛОР", "decided_at": "2026-07-11T00:00:00Z",
         "rationale": "verified"}
    r.update(over)
    return r


def _build(tmp_path, decisions, regimens):
    dxl = tmp_path / "dx.json"; dxl.write_text(json.dumps(_dx_ledger(decisions), ensure_ascii=False), encoding="utf-8")
    crl = tmp_path / "cr.json"; crl.write_text(json.dumps(_curated_regimens(regimens), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "ck.json"
    build_curated_knowledge.build(str(dxl), str(crl), str(out))
    return json.loads(out.read_text(encoding="utf-8"))


# ── build + query ──────────────────────────────────────────────


def test_build_links_diagnosis_to_regimens(tmp_path):
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")],
                 [_reg("5351", "1832"), _reg("5352", "1832")])
    assert doc["meta"]["status"] == "CURATED"
    ck = CuratedKnowledge(doc)
    res = ck.resolve("Эпиглоттит", None)
    assert isinstance(res, ApprovedChain)
    assert res.guideline_ids == ("1832",)
    assert {p["regimen_id"] for p in res.regimen_provenance} == {"5351", "5352"}
    # provenance preserved (req 4)
    p = res.regimen_provenance[0]
    for k in ("regimen_id", "guideline_id", "pdf_sha256", "pdf_path", "page_number"):
        assert p[k]


def test_no_duplicated_medical_content(tmp_path):
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [_reg("5351", "1832")])
    blob = json.dumps(doc, ensure_ascii=False)
    for forbidden in ("dose", "drug_normalized", "source_quote", "amoxicillin"):
        assert forbidden not in blob


def test_unknown_diagnosis_is_review_required(tmp_path):
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [_reg("5351", "1832")])
    res = CuratedKnowledge(doc).resolve("Неизвестный диагноз", None)
    assert isinstance(res, ReviewRequired)
    assert res.code == "NO_APPROVED_DIAGNOSIS"


def test_approved_diagnosis_without_regimen_is_review_required(tmp_path):
    # diagnosis approved to 1832, but no approved regimen for 1832
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [])
    res = CuratedKnowledge(doc).resolve("Эпиглоттит", None)
    assert isinstance(res, ReviewRequired)
    assert res.code == "NO_APPROVED_REGIMEN"


def test_determinism(tmp_path):
    d1 = _build(tmp_path / "a", [_dx_decision("D", "1")], [_reg("2", "1"), _reg("1", "1")]) \
        if (tmp_path / "a").mkdir() or True else None
    d2 = _build(tmp_path / "b", [_dx_decision("D", "1")], [_reg("1", "1"), _reg("2", "1")]) \
        if (tmp_path / "b").mkdir() or True else None
    assert d1["links"] == d2["links"]
    assert d1["approved_regimens"] == d2["approved_regimens"]


# ── CuratedEngine gate (req 3: never silently fall back) ────────


class _FakeCandidate:
    def __init__(self, rid, gid="1832"):
        # guideline_id is REQUIRED for the approval gate: a regimen_id is
        # unique only within a guideline (NormalizerDB PK is the pair).
        self.regimen_id = rid
        self.guideline_id = gid
        self.drug_ref = None


class _FakeRec:
    def __init__(self, rid, gid="1832"):
        self.candidate = _FakeCandidate(rid, gid)


class _FakeSet:
    def __init__(self, accepted, notes=(), excluded=(), safety_flags=(), warnings=(),
                 safety_summary=None):
        self.accepted = tuple(accepted); self.engine_notes = tuple(notes)
        self.excluded = tuple(excluded); self.safety_flags = tuple(safety_flags)
        self.warnings = tuple(warnings); self.safety_summary = safety_summary


class _FakeQuery:
    def __init__(self, dx, icd=None): self.diagnosis = dx; self.icd10 = icd


class _FakeEngine:
    def __init__(self, accepted): self._accepted = accepted
    def recommend(self, query): return _FakeSet(self._accepted)


import dataclasses as _dc  # noqa: E402
import clinical_engine.curated.knowledge as _k  # noqa: E402


def _patch_replace(monkeypatch):
    # CuratedEngine uses dataclasses.replace on BOTH the RecommendationSet and
    # (for re-ranking) the Recommendation; our fakes are not dataclasses, so
    # provide a compatible replace for the test.
    def fake_replace(obj, **kw):
        if not hasattr(obj, "accepted"):
            new = copy.copy(obj)
            for key, value in kw.items():
                setattr(new, key, value)
            return new
        return _FakeSet(
            kw.get("accepted", obj.accepted),
            kw.get("engine_notes", obj.engine_notes),
            kw.get("excluded", getattr(obj, "excluded", ())),
            kw.get("safety_flags", getattr(obj, "safety_flags", ())),
            kw.get("warnings", getattr(obj, "warnings", ())),
            kw.get("safety_summary", getattr(obj, "safety_summary", None)),
        )
    monkeypatch.setattr(_k.dataclasses, "replace", fake_replace)


def _note_stub(monkeypatch):
    class N:
        def __init__(self, code, message, stage, severity): self.code = code; self.message = message
    import clinical_engine.models as m
    monkeypatch.setattr(m, "EngineNote", N, raising=True)


def test_gate_review_required_when_diagnosis_unapproved(tmp_path, monkeypatch):
    _patch_replace(monkeypatch); _note_stub(monkeypatch)
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [_reg("5351", "1832")])
    eng = CuratedEngine(_FakeEngine([_FakeRec("5351")]), CuratedKnowledge(doc))
    out = eng.recommend(_FakeQuery("Неизвестный"))
    assert out.accepted == ()
    assert any(n.code == "REVIEW_REQUIRED" for n in out.engine_notes)


def test_icd_only_query_resolves_through_the_engine_index(tmp_path, monkeypatch):
    """M-5 end-to-end: api/contract.py permits an ICD-only request, and the
    shipped curated artifact keys approvals by diagnosis NAME, so the code is
    mapped to names via the engine's own diagnosis index. Still fail-closed."""
    _note_stub(monkeypatch)
    doc = _build(tmp_path, [_dx_decision("Острый цистит", "1127")], [_reg("7001", "1127")])
    ck = CuratedKnowledge(doc)

    class _IndexEngine:
        """Stands in for Engine: exposes the public ICD->names helper."""

        def guideline_diagnosis_names(self, icd10):
            return ("Острый цистит",) if icd10.upper() == "N30.0" else ()

        def recommend(self, query):
            return _FakeSet(())

    eng = CuratedEngine(_IndexEngine(), ck)
    chain = eng._resolve_chain(_FakeQuery(None, "N30.0"), None)
    assert isinstance(chain, ApprovedChain)
    assert chain.guideline_ids == ("1127",)
    assert chain.approved_keys() == {("1127", "7001")}

    # An ICD the index does not know stays fail-closed.
    unknown = eng._resolve_chain(_FakeQuery(None, "Z99"), None)
    assert isinstance(unknown, ReviewRequired)
    assert unknown.code == "NO_APPROVED_DIAGNOSIS"


def test_icd_only_request_returns_approved_recommendations(tmp_path, monkeypatch):
    _patch_replace(monkeypatch); _note_stub(monkeypatch)
    doc = _build(tmp_path, [_dx_decision("Острый цистит", "1127")], [_reg("7001", "1127")])
    ck = CuratedKnowledge(doc)

    class _Engine:
        def guideline_diagnosis_names(self, icd10):
            return ("Острый цистит",)

        def recommend(self, query):
            return _FakeSet(accepted=(_FakeRec("7001", "1127"),))

    out = CuratedEngine(_Engine(), ck).recommend(_FakeQuery(None, "N30.0"))
    assert [r.candidate.regimen_id for r in out.accepted] == ["7001"]
    assert not any(n.code == "REVIEW_REQUIRED" for n in out.engine_notes)


def test_renumbered_ranks_and_narrowed_flags(tmp_path, monkeypatch):
    """M-6: the returned set is described by the returned set."""
    _patch_replace(monkeypatch); _note_stub(monkeypatch)
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [_reg("5351", "1832")])
    ck = CuratedKnowledge(doc)

    class _Engine:
        def recommend(self, query):
            return _FakeSet(accepted=(_FakeRec("5351", "1832"), _FakeRec("9999", "1832")))

    out = CuratedEngine(_Engine(), ck).recommend(_FakeQuery("Эпиглоттит"))
    assert [r.rank for r in out.accepted] == [1]  # no gap left by the filter
    assert out.safety_summary is not None


def test_gate_withholds_unapproved_regimen(tmp_path, monkeypatch):
    _patch_replace(monkeypatch); _note_stub(monkeypatch)
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [_reg("5351", "1832")])
    # engine returns an approved (5351) and an UNapproved (9999) rec
    eng = CuratedEngine(_FakeEngine([_FakeRec("5351"), _FakeRec("9999")]), CuratedKnowledge(doc))
    out = eng.recommend(_FakeQuery("Эпиглоттит"))
    assert {r.candidate.regimen_id for r in out.accepted} == {"5351"}  # 9999 withheld
    assert any(n.code == "CURATED_APPROVED" for n in out.engine_notes)


def test_gate_withholds_same_regimen_id_under_a_different_guideline(tmp_path, monkeypatch):
    """regimen_id is NOT globally unique (PK is (guideline_id, regimen_id)).

    Approving "r1" under guideline A must not approve an unapproved "r1" under
    guideline B. The old gate filtered a GLOBAL approved-id set against
    `candidate.regimen_id` alone, so B's unapproved r1 passed.
    """
    _patch_replace(monkeypatch); _note_stub(monkeypatch)
    # Guideline A (1832) has approved r1. Guideline B (9999) reuses the same
    # regimen_id but appears in NO approved_regimens row at all.
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [_reg("r1", "1832")])
    ck = CuratedKnowledge(doc)
    assert ck.approved_regimen_keys() == {("1832", "r1")}

    eng = CuratedEngine(_FakeEngine([_FakeRec("r1", "1832"), _FakeRec("r1", "9999")]), ck)
    out = eng.recommend(_FakeQuery("Эпиглоттит"))
    kept = [(r.candidate.guideline_id, r.candidate.regimen_id) for r in out.accepted]
    assert kept == [("1832", "r1")]
    withheld = {r.candidate.guideline_id for r, _ in out.excluded}
    assert "9999" in withheld


def test_withheld_recommendations_move_into_excluded(tmp_path, monkeypatch):
    """M-6: accepted is filtered, so excluded/warnings/flags/rank must describe
    the RETURNED set, not the pre-filter one."""
    _patch_replace(monkeypatch); _note_stub(monkeypatch)
    doc = _build(tmp_path, [_dx_decision("Эпиглоттит", "1832")], [_reg("5351", "1832")])
    eng = CuratedEngine(_FakeEngine([_FakeRec("5351"), _FakeRec("9999")]), CuratedKnowledge(doc))
    out = eng.recommend(_FakeQuery("Эпиглоттит"))
    assert [r.candidate.regimen_id for r, _ in out.excluded] == ["9999"]
    assert all("not approved under guideline" in reason for _, reason in out.excluded)


def test_icd_only_query_resolves_when_approved_row_carries_codes(tmp_path):
    """M-5: an ICD-only request is explicitly permitted by api/contract.py."""
    decision = _dx_decision("Острый цистит", "1127")
    doc = _build(tmp_path, [decision], [_reg("7001", "1127")])
    doc["approved_diagnoses"][0]["icd10_codes"] = ["N30.0", "N30"]
    ck = CuratedKnowledge(doc)
    assert ck.approved_guideline_ids(None, "N30.0") == ["1127"]
    assert ck.approved_guideline_ids(None, "N30") == ["1127"]
    assert ck.approved_guideline_ids("Острый цистит", "N30") == ["1127"]
    res = ck.resolve(None, "N30.0")
    assert isinstance(res, ApprovedChain)
    assert res.guideline_ids == ("1127",)
    # Still fail-closed for an unknown code.
    assert ck.approved_guideline_ids(None, "Z99") == []
    assert isinstance(ck.resolve(None, "Z99"), ReviewRequired)


def test_gate_review_required_when_knowledge_missing(monkeypatch):
    _patch_replace(monkeypatch); _note_stub(monkeypatch)
    eng = CuratedEngine(_FakeEngine([_FakeRec("5351")]), None)
    out = eng.recommend(_FakeQuery("Эпиглоттит"))
    assert out.accepted == ()
    assert any(n.code == "REVIEW_REQUIRED" for n in out.engine_notes)


# ── cross-layer validation (req 6) ─────────────────────────────


def test_validate_clean(tmp_path):
    doc = _build(tmp_path, [_dx_decision("D", "1")], [_reg("2", "1")])
    assert validate_curated_knowledge.validate(doc)["clean"] is True


def test_validate_approved_diagnosis_missing_regimen(tmp_path):
    doc = _build(tmp_path, [_dx_decision("D", "1")], [_reg("2", "2")])  # dx->1, reg->2
    r = validate_curated_knowledge.validate(doc)
    assert r["errors_by_type"].get("APPROVED_DIAGNOSIS_MISSING_REGIMEN") == 1
    assert r["errors_by_type"].get("APPROVED_REGIMEN_MISSING_DIAGNOSIS") == 1


def test_validate_provenance_broken(tmp_path):
    doc = _build(tmp_path, [_dx_decision("D", "1")], [_reg("2", "1", pdf_sha256="")])
    r = validate_curated_knowledge.validate(doc)
    assert r["errors_by_type"].get("PROVENANCE_CHAIN_BROKEN") == 1


def test_validate_missing_physician_approval(tmp_path):
    doc = _build(tmp_path, [_dx_decision("D", "1")], [_reg("2", "1", decided_by="")])
    r = validate_curated_knowledge.validate(doc)
    assert r["errors_by_type"].get("PHYSICIAN_APPROVAL_MISSING") == 1


# ── backward compatibility ─────────────────────────────────────


def test_plain_engine_module_unchanged():
    # The base Engine must not import or depend on the curated layer (additive-only).
    import re
    import clinical_engine.engine as engine_mod
    src = Path(engine_mod.__file__).read_text(encoding="utf-8")
    assert not re.search(r"(from|import)\s+clinical_engine\.curated", src)
    assert "CuratedEngine" not in src and "CuratedKnowledge" not in src
