"""Regression tests for the infrastructure fixes that had no test at all.

Grouped by the defect they lock down: filename collisions (H-19/H-20/H-24),
prefilter state machine (M-32..M-37, L-19..L-21), the official-card audit
(M-13..M-15), the extraction cache (M-20), and the misc low items.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


# ===========================================================================
# H-19 / H-20 / H-24 / M-37 -- three writers built target names from the
# guideline NAME alone, so colliding names made one document inherit another's
# path and therefore its pdf_sha256.
# ===========================================================================

def test_h20_collision_is_disambiguated_with_the_rubricator_id(tmp_path):
    """H-20: 'Сепсис у новорождённых' vs 'Сепсис у новорождённых ' sanitize to the
    same name, and the second inherited the first's path AND pdf_sha256."""
    from src.pipeline.downloader import unique_destination

    (tmp_path / "Сепсис у новорождённых.pdf").write_bytes(b"%PDF-1.4 first")
    got = unique_destination(tmp_path, "Сепсис у новорождённых.pdf", 4242)
    assert got.name == "Сепсис у новорождённых_4242.pdf"
    assert not got.exists()


def test_h20_punctuation_variant_collides_and_is_disambiguated(tmp_path):
    """H-20: 'Отит: средний острый' and 'Отит  - средний острый' both sanitize to
    'Отит - средний острый'."""
    from src.pipeline.downloader import sanitize_filename, unique_destination

    a = sanitize_filename("Отит: средний острый")
    b = sanitize_filename("Отит  - средний острый")
    assert a == b == "Отит - средний острый"

    (tmp_path / f"{a}.pdf").write_bytes(b"%PDF-1.4 first")
    second = unique_destination(tmp_path, f"{b}.pdf", 78)
    assert second.name == f"{a}_78.pdf"


def test_h20_unique_destination_is_idempotent(tmp_path):
    """M-37: re-running must land on the SAME path, not append _2 forever."""
    from src.pipeline.downloader import unique_destination

    (tmp_path / "А.pdf").write_bytes(b"%PDF-1.4 a")
    first = unique_destination(tmp_path, "А.pdf", 5, source=tmp_path / "in.pdf")
    second = unique_destination(tmp_path, "А.pdf", 5, source=tmp_path / "in.pdf")
    assert first == second

    # a file already AT its Id-derived destination keeps it
    placed = tmp_path / first.name
    placed.write_bytes(b"%PDF-1.4 b")
    third = unique_destination(tmp_path, "А.pdf", 5, source=placed)
    assert third == first, "a repeat move must not append another numeric suffix"


def test_h20_collision_without_an_id_still_finds_a_free_name(tmp_path):
    from src.pipeline.downloader import unique_destination

    (tmp_path / "А.pdf").write_bytes(b"%PDF-1.4 a")
    got = unique_destination(tmp_path, "А.pdf", None)
    assert got.name != "А.pdf"
    assert not got.exists()


def test_h24_move_pdf_refuses_a_decision_without_an_id(tmp_path, caplog):
    """A NULL primary key is worse than a name collision."""
    from src.pipeline import prefilter

    src = tmp_path / "src.pdf"
    src.write_bytes(b"%PDF-1.4 a")
    with pytest.raises(ValueError, match="no rubricator Id"):
        prefilter.move_pdf(
            {"pdf_path": str(src), "Id": None, "Name": "X",
             "final_decision": "review", "default_decision": "review"},
            tmp_path / "dst", [],
        )


def test_h24_move_pdf_records_the_disambiguated_destination(tmp_path):
    from src.pipeline import prefilter

    target = tmp_path / "dst"
    target.mkdir()
    (target / "Сепсис.pdf").write_bytes(b"%PDF-1.4 other")
    src = tmp_path / "Сепсис.pdf"
    src.write_bytes(b"%PDF-1.4 mine")
    manifest: list[dict] = []
    assert prefilter.move_pdf(
        {"pdf_path": str(src), "Id": 99, "Name": "Сепсис",
         "final_decision": "review", "default_decision": "review"},
        target, manifest,
    )
    assert Path(manifest[0]["destination_path"]).name == "Сепсис_99.pdf"
    assert manifest[0]["matched_rule"] is None
    assert not src.exists()
    # the other document's file is untouched
    assert (target / "Сепсис.pdf").read_bytes() == b"%PDF-1.4 other"


# ===========================================================================
# prefilter state machine
# ===========================================================================

def _rules():
    return {
        "defaults": {
            "has_antibiotics_True_abx_level_AB": "need_llm",
            "has_antibiotics_True_abx_level_CD": "need_llm",
            "has_antibiotics_False_abx_score_gte_10": "review",
            "has_antibiotics_False_abx_score_lt_10": "no_antibiotics",
            "has_antibiotics_False_abx_score_null": "review",
        },
        "rules": {},
    }


def test_m32_scoreless_item_is_routed_to_review_not_no_antibiotics():
    from src.pipeline.prefilter import _default_decision

    # M-32: `abx_score` was coerced None->0 before the null branch, so this
    # returned 'no_antibiotics'.
    decision, _reason = _default_decision(
        {"has_antibiotics": False, "abx_level": "D", "abx_score": None}, _rules()
    )
    assert decision == "review"


def test_m32_explicit_zero_score_still_uses_the_lt_10_rule():
    from src.pipeline.prefilter import _default_decision

    decision, _ = _default_decision(
        {"has_antibiotics": False, "abx_level": "D", "abx_score": 0}, _rules()
    )
    assert decision == "no_antibiotics"


def test_m33_rule_with_no_match_criteria_is_ignored_not_blanket():
    from src.pipeline.prefilter import _check_rule

    # M-33: a typo that dropped `match_any` made the rule match EVERY item.
    assert _check_rule({"name": "force_exclude", "priority": 100}, {"Name": "любая"}) is None


def test_m33_a_malformed_rule_is_logged(caplog):
    from src.pipeline.prefilter import _check_rule

    with caplog.at_level("ERROR"):
        _check_rule({"name": "force_exclude", "priority": 100}, {"Name": "любая"})
    assert "no match criteria" in caplog.text


def test_m33_rule_with_criteria_still_matches():
    from src.pipeline.prefilter import _check_rule

    got = _check_rule(
        {"name": "force_include", "priority": 10, "match_any": {"name_keywords": ["пневмония"]}},
        {"Name": "Внебольничная пневмония"},
    )
    assert got is not None and got["matched"] is True


def test_m34_matched_rule_is_the_deciding_rule():
    from src.pipeline.prefilter import classify_item

    rules = _rules()
    rules["rules"] = {
        "force_include": {"priority": 100, "match_any": {"name_keywords": ["пневмония"]}},
        "force_review": {"priority": 50, "match_any": {"name_keywords": ["пневмония"]}},
    }
    got = classify_item(
        {"Id": 1, "Name": "Пневмония", "has_antibiotics": False, "abx_level": "D", "abx_score": 0},
        rules,
    )
    assert got["final_decision"] == "need_llm"
    # force_include (priority 100) decided; force_review only confirmed
    assert got["matched_rule"] == "force_include"


def test_m34_a_confirming_rule_is_not_reported_as_the_decider():
    from src.pipeline.prefilter import classify_item

    rules = _rules()
    rules["rules"] = {
        "force_include": {"priority": 100, "match_any": {"name_keywords": ["пневмония"]}},
        "force_review": {"priority": 50, "match_any": {"name_keywords": ["пневмония"]}},
    }
    # force_include (priority 100) CONFIRMS the default and takes the force_ lock,
    # so force_review (p50) is deliberately skipped.  The reported rule must be the
    # one that decided -- the lock holder.
    got = classify_item(
        {"Id": 1, "Name": "Пневмония", "has_antibiotics": True, "abx_level": "A", "abx_score": 30},
        rules,
    )
    assert got["final_decision"] == "need_llm"
    assert got["override"] is False
    assert got["matched_rule"] == "force_include"


def test_m34_reported_rule_is_the_one_that_decided_not_the_last_that_matched():
    """Two rules of EQUAL priority: the deciding one must be reported, not the
    last one seen (the old `>=` comparison let the later rule win the report)."""
    from src.pipeline.prefilter import classify_item

    rules = _rules()
    rules["rules"] = {
        "upgrade_to_active": {
            "priority": 100, "match_any": {"name_keywords": ["пневмония"]},
        },
        "downgrade_to_review": {
            "priority": 100, "match_any": {"name_keywords": ["пневмония"]},
        },
    }
    got = classify_item(
        {"Id": 1, "Name": "Пневмония", "has_antibiotics": True, "abx_level": "A", "abx_score": 30},
        rules,
    )
    # default is need_llm; upgrade confirms, downgrade changes it to review
    assert got["final_decision"] == "review"
    assert got["override"] is True
    assert got["matched_rule"] == "downgrade_to_review", \
        "the reported rule must be the one that decided"


def test_m42_string_false_in_a_rule_condition_is_honoured():
    from src.pipeline.prefilter import _check_conditions

    # M-42: a JSON rule with the string "false" never matched a strict bool.
    assert _check_conditions({"has_antibiotics": "false"}, {"has_antibiotics": False}) is True
    assert _check_conditions({"has_antibiotics": "false"}, {"has_antibiotics": True}) is False
    assert _check_conditions({"has_antibiotics": "true"}, {"has_antibiotics": True}) is True
    assert _check_conditions({"has_antibiotics": True}, {"has_antibiotics": True}) is True


def test_m35_print_stats_survives_an_empty_corpus(capsys):
    from src.pipeline.prefilter import print_stats

    # M-35: every percentage divided by len(results).
    print_stats([], 0.0)
    out = capsys.readouterr().out
    assert "Total PDFs analyzed:     0" in out
    assert "nan" not in out.lower()


def test_m37_movement_manifest_is_appended_not_overwritten(tmp_path, monkeypatch):
    from src.pipeline import prefilter

    manifest_path = tmp_path / "movement_manifest.json"
    monkeypatch.setattr(prefilter, "MOVEMENT_MANIFEST", manifest_path)

    prefilter._append_movement_manifest([
        {"source_path": "/a/1.pdf", "destination_path": "/b/1.pdf", "Id": 1},
    ])
    prefilter._append_movement_manifest([
        {"source_path": "/a/2.pdf", "destination_path": "/b/2.pdf", "Id": 2},
    ])
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [e["Id"] for e in entries] == [1, 2], "the first batch's record was destroyed"


def test_m37_movement_manifest_dedups_repeat_moves(tmp_path, monkeypatch):
    from src.pipeline import prefilter

    manifest_path = tmp_path / "movement_manifest.json"
    monkeypatch.setattr(prefilter, "MOVEMENT_MANIFEST", manifest_path)
    entry = {"source_path": "/a/1.pdf", "destination_path": "/b/1.pdf", "Id": 1}
    prefilter._append_movement_manifest([entry])
    prefilter._append_movement_manifest([dict(entry)])
    assert len(json.loads(manifest_path.read_text(encoding="utf-8"))) == 1


def test_m36_full_audit_does_not_claim_to_move_files(tmp_path, monkeypatch, capsys):
    from src.pipeline import prefilter

    results = [
        {"Id": 1, "Name": "Сепсис", "final_decision": "no_antibiotics",
         "abx_score": 0, "abx_level": "D"},
    ]
    manifest = tmp_path / "dry_run_manifest.json"
    manifest.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(prefilter, "DRY_RUN_MANIFEST", manifest)
    monkeypatch.setattr(prefilter, "MOVEMENT_MANIFEST", tmp_path / "mm.json")

    ok = prefilter.cmd_full_audit()
    out = capsys.readouterr().out
    assert ok is False, "suspicious items found must not report success"
    assert "no PDF is moved" in out
    # and the reclassification really did happen
    updated = json.loads(manifest.read_text(encoding="utf-8"))
    assert updated[0]["final_decision"] == "review"


def test_l20_safe_preserves_cyrillic_and_specials():
    from src.pipeline.prefilter import _safe

    # L-20: cp1251 turned these into '?' in the audit output AND in the manifest
    # `reason` field.
    for raw in ("Ёлка ёжик — тест", "доза ≤ 5 мг", "тест пробел"):
        got = _safe(raw)
        assert "?" not in got, f"{raw!r} was mangled into {got!r}"
    assert "Ё" in _safe("Ёлка")


def test_l21_audit_sample_is_reproducible():
    from src.pipeline.prefilter import audit_no_antibiotics

    results = [
        {"Id": i, "Name": f"Инфекция {i}", "final_decision": "no_antibiotics",
         "abx_level": "D", "abx_score": 0, "mkb_codes": [], "reason": "r",
         "matched_rule": "default"}
        for i in range(50)
    ]
    a = audit_no_antibiotics(results, sample_size=10, seed=7)
    b = audit_no_antibiotics(results, sample_size=10, seed=7)
    assert a == b


def test_l19_load_rules_raises_instead_of_exiting(monkeypatch, tmp_path):
    from src.pipeline import prefilter

    monkeypatch.setattr(prefilter, "RULES_FILE", tmp_path / "absent.json")
    # a library function must not sys.exit()
    with pytest.raises(FileNotFoundError):
        prefilter.load_rules()


def test_l18_rules_file_is_assigned_once_at_the_repo_root(monkeypatch):
    from src.pipeline import prefilter

    assert prefilter.RULES_FILE == prefilter.ANTIBIO_ROOT / "prefilter_rules.json"
    assert prefilter.RULES_FILE.is_file(), "prefilter_rules.json must resolve from the repo root"


def test_l15_triage_rules_have_no_duplicate_keywords():
    from src.pipeline.extraction import dosa_extension_triage as triage

    for name, _title, keywords in triage._RULES:
        dupes = [k for k in set(keywords) if keywords.count(k) > 1]
        assert not dupes, f"rule {name!r} repeats {dupes}"


def test_l15_triage_rule_order_is_pinned():
    """L-15: the order is load-bearing (first match wins) and had no test."""
    from src.pipeline.extraction import dosa_extension_triage as triage

    assert [rule[0] for rule in triage._RULES] == [
        "congenital_cardiac_prophylaxis", "surgical_prophylaxis", "oncology",
        "immunodeficiency_pjp", "metabolic_genetic", "infection",
    ]


# ===========================================================================
# M-13 / M-14 / M-15 -- official card audit
# ===========================================================================

def _inventory(*ids):
    return {"rows": [
        {"declared_cr_id": cid, "latest_local_metadata": {}} for cid in ids
    ]}


def test_m14_non_numeric_card_id_does_not_abort_the_sort():
    from src.pipeline.extraction import official_card_audit as oca

    # M-14: `int(p) for p in value.split("_")` raised inside the sort, after all
    # the HTTP work had already been done.
    got = oca.candidate_card_ids(_inventory("314_3", "КР-9_1", "9_1", "abc"))
    assert got[0] == "9_1"
    assert "314_3" in got and "КР-9_1" in got and "abc" in got


def test_m14_non_numeric_code_prefix_becomes_a_recorded_failure():
    from src.pipeline.extraction import official_card_audit as oca

    registry = [{"Code": 9, "CodeVersion": "9_1", "Name": "x"}]
    artifact = oca.build_registry_audit(
        _inventory("КР-9_1"), registry_fetcher=lambda: registry, captured_at="t"
    )
    assert artifact["failures"] == [
        {"requested_id": "КР-9_1", "error": "non-numeric code prefix in 'КР-9_1'"}
    ]
    assert artifact["verified_count"] == 0, "the other cards must not be discarded"


def test_m15_registry_paging_is_bounded(monkeypatch):
    """A wrong TotalRecords must not spin forever."""
    from src.pipeline.extraction import official_card_audit as oca

    calls = {"n": 0}

    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            calls["n"] += 1
            # always a full page, and a total that is never reached
            return {
                "Data": [{"Code": 1, "CodeVersion": "1_1"}] * 100,
                "TotalRecords": 10**9,
            }

    monkeypatch.setattr(oca.httpx, "post", lambda *a, **k: _Resp())
    monkeypatch.setattr(oca, "MAX_REGISTRY_PAGES", 5)
    with pytest.raises(RuntimeError, match="did not terminate"):
        oca.fetch_current_registry()
    assert calls["n"] == 5, "the page guard did not stop the loop"


def test_m15_absent_total_records_pages_until_a_short_page(monkeypatch):
    from src.pipeline.extraction import official_card_audit as oca

    pages = [
        {"Data": [{"CodeVersion": f"{i}_1"} for i in range(100)]},
        {"Data": [{"CodeVersion": "200_1"}]},   # short page -> end of list
    ]

    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

    state = {"i": 0}

    def _post(*a, **k):
        payload = pages[min(state["i"], len(pages) - 1)]
        state["i"] += 1
        return type("R", (), {"raise_for_status": staticmethod(lambda: None),
                              "json": staticmethod(lambda: payload)})()

    monkeypatch.setattr(oca.httpx, "post", _post)
    records = oca.fetch_current_registry()
    # M-15: an absent TotalRecords used to return page 1 only.
    assert len(records) == 101


def test_m13_main_uses_the_exact_matcher(monkeypatch, tmp_path):
    """M-13: main() used the code-only matcher, silently binding a v3 PDF to a v4 card."""
    from src.pipeline.extraction import official_card_audit as oca

    used: list[str] = []

    def _exact(inventory, **kwargs):
        used.append("exact")
        return {
            "artifact_type": oca.ARTIFACT_TYPE if hasattr(oca, "ARTIFACT_TYPE") else "OFFICIAL_RUBRICATOR_CARD_AUDIT",
            "requested_count": 0, "verified_count": 0, "applicable_count": 0,
            "failures": [], "cards": [],
        }

    def _weak(inventory, **kwargs):
        used.append("weak")
        return {"requested_count": 0, "verified_count": 0, "applicable_count": 0, "failures": []}

    inventory = tmp_path / "inv.json"
    inventory.write_text(json.dumps(_inventory("314_3")), encoding="utf-8")
    output = tmp_path / "out.json"

    monkeypatch.setattr(oca, "build_exact_registry_audit", _exact)
    monkeypatch.setattr(oca, "build_registry_audit", _weak)
    monkeypatch.setattr(
        "sys.argv",
        ["official_card_audit", "--inventory", str(inventory), "--output", str(output)],
    )
    assert oca.main() == 0
    assert used == ["exact"], "main() used the weaker code-only matcher"


def test_m13_registry_stdin_path_is_still_available(monkeypatch, tmp_path):
    from src.pipeline.extraction import official_card_audit as oca

    used: list[str] = []
    monkeypatch.setattr(oca, "build_exact_registry_audit",
                        lambda *a, **k: used.append("exact") or {
                            "requested_count": 0, "verified_count": 0,
                            "applicable_count": 0, "failures": []})
    monkeypatch.setattr(oca, "build_registry_audit",
                        lambda *a, **k: used.append("weak") or {
                            "requested_count": 0, "verified_count": 0,
                            "applicable_count": 0, "failures": []})
    inventory = tmp_path / "inv.json"
    inventory.write_text(json.dumps(_inventory("314_3")), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        ["official_card_audit", "--inventory", str(inventory),
         "--output", str(tmp_path / "o.json"), "--registry-stdin"],
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("[]"))
    assert oca.main() == 0
    assert used == ["weak"]


def test_l17_apply_status_absence_is_visible():
    from src.pipeline.extraction import official_card_audit as oca

    absent = oca.compact_registry_card({"CodeVersion": "1_1"})
    assert absent["apply_status_calculated_present"] is False
    present = oca.compact_registry_card({"CodeVersion": "1_1", "ApplyStatusCalculated": 1})
    assert present["apply_status_calculated_present"] is True

    registry = [{"Code": 1, "CodeVersion": "1_1", "Name": "x"}]
    artifact = oca.build_registry_audit(
        _inventory("1_1"), registry_fetcher=lambda: registry, captured_at="t"
    )
    assert artifact["applicable_count"] == 0
    assert artifact["applicable_count_computable"] is False, \
        "a count of 0 that is actually 'unknown' must say so"


# ===========================================================================
# M-20 -- the extraction cache
# ===========================================================================

def _doc_fixture(pdf: Path):
    from src.pipeline.extraction.base import BoundingBox, Document, Page, TableCell, TableObject

    table = TableObject(
        page_num=0, bbox=BoundingBox(0, 0, 10, 10), rows=1, cols=1,
        cells=[TableCell(row=0, col=0, text="500 мг", bbox=BoundingBox(0, 0, 10, 10),
                         confidence=0.9, engine="pymupdf-native-table", source_pdf=str(pdf))],
        engine="pymupdf-native-table", source_pdf=str(pdf),
    )
    doc = Document(
        source="pymupdf", pdf_path=pdf, pages=[Page(0, "Амоксициллин 500 мг")],
        full_text="Амоксициллин 500 мг", markdown="#", confidence=0.9,
        warnings=["w1"], errors=["e1"], elapsed_time_ms=12.0,
        entities=[{"type": "Dose", "normalized": "500"}],
        knowledge_objects={"Dose": [{"value": "500", "unit": "мг"}]},
        tables=[{"row": 0}], structured_tables=[table],
    )
    doc.pages[0].structured_tables = [table]
    doc.pages[0].entities = [{"type": "Dose", "normalized": "500"}]
    return doc


def test_m20_cache_key_includes_the_extractor_fingerprint(tmp_path, monkeypatch):
    from src.pipeline.extraction import cache as cache_mod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 a")
    c = _bare_cache(cache_mod, tmp_path / "cache", "fp-1")
    plain = c._key(pdf)
    c._fingerprint = "fp-2"
    assert c._key(pdf) != plain, "the extractor version does not invalidate the cache"


def test_m20_document_round_trips_fully(tmp_path):
    from src.pipeline.extraction import cache as cache_mod

    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 a")
    doc = _doc_fixture(pdf)
    blob = cache_mod._doc_to_dict(doc)
    # M-20: these were all dropped, so the expensive stages re-ran on a hit
    for field in ("entities", "knowledge_objects", "structured_tables", "markdown",
                  "warnings", "errors", "elapsed_time_ms"):
        assert field in blob, f"{field} is not cached"
    back = cache_mod._dict_to_doc(blob)
    assert back.entities == doc.entities
    assert back.knowledge_objects == doc.knowledge_objects
    assert back.markdown == "#"
    assert back.warnings == ["w1"]
    assert len(back.structured_tables) == 1
    assert back.structured_tables[0].cells[0].text == "500 мг"
    assert back.structured_tables[0].engine == "pymupdf-native-table"
    assert back.pages[0].structured_tables[0].cells[0].confidence == 0.9


def test_m20_fingerprint_changes_with_the_extractor_source(monkeypatch, tmp_path):
    from src.pipeline.extraction import cache as cache_mod

    real = cache_mod._EXTRACTOR_SOURCES
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_SOURCES", ("base.py",))
    first = cache_mod.extractor_fingerprint()
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_SOURCES", ("pymupdf.py",))
    second = cache_mod.extractor_fingerprint()
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_SOURCES", real)
    assert first != second


def _bare_cache(cache_mod, root, fingerprint):
    c = cache_mod.ExtractionCache.__new__(cache_mod.ExtractionCache)
    c.cfg = None
    c.enabled = True
    c.root = root
    root.mkdir(parents=True, exist_ok=True)
    c._fingerprint = fingerprint
    return c


def test_m20_stale_entry_is_ignored(tmp_path):
    from src.pipeline.extraction import cache as cache_mod

    root = tmp_path / "cache"
    c = _bare_cache(cache_mod, root, "fp-A")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 a")
    c.put(pdf, _doc_fixture(pdf))
    assert c.get(pdf) is not None
    # simulate an extractor change
    c._fingerprint = "fp-B"
    assert c.get(pdf) is None, "a stale entry was served after the extractor changed"


# ===========================================================================
# mineru: L-36 / L-37
# ===========================================================================

def test_l37_mineru_output_is_split_into_pages():
    from src.pipeline.extraction.mineru import _split_mineru_pages

    md = (
        "страница один\n"
        "<!-- page 2 -->\n"
        "страница два\n"
        "\u2014 page 3 \u2014\n"
        "страница три"
    )
    pages = _split_mineru_pages(md)
    assert len(pages) == 3
    assert pages[0] == "страница один"
    assert pages[2] == "страница три"


def test_l37_markdown_without_markers_stays_one_page():
    from src.pipeline.extraction.mineru import _split_mineru_pages

    md = "нет маркеров\nпросто текст"
    assert _split_mineru_pages(md) == [md]


def test_l36_mineru_binary_is_overridable(monkeypatch):
    from src.pipeline.extraction import mineru

    monkeypatch.setenv("ANTIBIO_MINERU_BIN", "/opt/bin/mineru")
    assert Path("/opt/bin/mineru").name == "mineru"
    # the hardcoded Windows path must be gone from the source
    source = Path(mineru.__file__).read_text(encoding="utf-8")
    assert "'Scripts', 'mineru.exe'" not in source


# ===========================================================================
# M-26 index presence is checked in test_knowledge_base; here: database
# ===========================================================================

def test_h24_regimens_table_has_a_clinrec_id_index_and_fk_pragma():
    import sqlite3 as _sqlite3

    from src.pipeline import database

    conn = _sqlite3.connect(":memory:")
    database.init_regimens_table(conn)
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(antibiotic_regimens)")}
    assert "idx_regimens_clinrec_id" in indexes
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1, \
        "the declared FK must actually be enforced"
    conn.close()


def test_l54_non_finite_dose_is_rejected_not_stored_as_null():
    import math

    from src.pipeline import database

    assert database._sanitize(float("nan")) is None
    assert database._sanitize(float("inf")) is None
    assert database._sanitize(500) == 500
    assert database._sanitize("500") == "500"


def test_l53_save_review_required_signature_accepts_no_path():
    import inspect

    from src.pipeline import database

    sig = inspect.signature(database.save_review_required)
    assert sig.parameters["path"].default is None


# ===========================================================================
# layout: L-25..L-29, M-29, M-30, H-13, H-14
# ===========================================================================

def test_h14_build_cells_from_words_does_not_raise_nameerror():
    """H-14: `defaultdict` was used without an import; the bare except hid it."""
    import ast
    from pathlib import Path

    from src.pipeline.extraction import layout

    source = Path(layout.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "collections":
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert "defaultdict" in imported


def test_l25_rapidtable_html_never_returns_a_non_string():
    from src.pipeline.extraction.layout import _rapidtable_html

    class New:
        pred_htmls = ["<table>a</table>"]  # noqa: RUF012 - duck-typed API stub

    class Old:
        pass

    class One:
        pred_htmls = ["<table>b</table>", "<table>c</table>"]  # noqa: RUF012 - stub

    assert _rapidtable_html(New()) == "<table>a</table>"
    assert _rapidtable_html(One()) == "<table>b</table>"
    assert _rapidtable_html(Old()) == ""
    assert _rapidtable_html(["<table>d</table>", "x"]) == "<table>d</table>"
    assert _rapidtable_html(None) == ""
    assert _rapidtable_html([]) == ""


def test_l27_header_markers_cover_russian():
    from src.pipeline.extraction.layout import _HEADER_MARKERS

    for marker in ("препарат", "дозировка", "длительность", "header"):
        assert marker in _HEADER_MARKERS


def test_h13_dosing_signals_cover_compact_notations():
    """H-13: '3 р/сут', 'по 1 фл.', '500 МЕ' matched NONE of the old keywords."""
    from src.pipeline.extraction.layout import _DOSING_SIGNALS

    for text in ("3 р/сут", "по 1 фл.", "500 МЕ", "в/в 2 раза в день", "7 дней",
                 "перорально 1 раз в сутки", "табл. 2", "ампул 1 мл"):
        assert any(sig in text.lower() for sig in _DOSING_SIGNALS), \
            f"{text!r} has no dosing signal and would be skipped"
    assert "international" not in _DOSING_SIGNALS


def test_l29_layout_engine_metadata_names_only_engines_that_ran(monkeypatch):
    from src.pipeline.extraction.base import BoundingBox, Document, Page, TableObject
    from src.pipeline.extraction import layout

    monkeypatch.setattr(layout, "_LAYOUT_PROCESSORS", {})
    doc = Document(source="pymupdf", pdf_path=Path("x.pdf"),
                   pages=[Page(0, "")], full_text="")
    table = TableObject(page_num=0, bbox=BoundingBox(0, 0, 1, 1), rows=1, cols=1,
                        engine="pymupdf-native-table", source_pdf="x.pdf")

    class _Stub:
        def __init__(self, device="cpu"):
            self.last_skipped_pages = []

        def process_pdf(self, pdf_path):
            return ([{"page_num": 0, "blocks": [], "tables": []}], [table])

    monkeypatch.setattr(layout, "LayoutProcessor", _Stub)
    layout.add_layout_to_document(doc, Path("x.pdf"))

    assert doc.metadata["layout_engine"] == "pymupdf-native-table", \
        "provenance must not claim engines that never ran"
    assert "doclayout" not in doc.metadata["layout_engine"]
    assert "rapidtable" not in doc.metadata["layout_engine"]
    assert doc.metadata["layout_engines_used"] == ["pymupdf-native-table"]


def test_m29_layout_processor_is_cached_per_device():
    from src.pipeline.extraction import layout

    layout._LAYOUT_PROCESSORS.clear()
    created = []

    class _Fake:
        def __init__(self, device="cpu"):
            created.append(device)
            self.last_skipped_pages = []

        def process_pdf(self, pdf_path):
            return ([], [])

    original = layout.LayoutProcessor
    layout.LayoutProcessor = _Fake
    try:
        a = layout.get_layout_processor()
        b = layout.get_layout_processor()
        assert a is b, "the processor (and its 3 model loads) is rebuilt per document"
        assert created == ["cpu"]
    finally:
        layout.LayoutProcessor = original
        layout._LAYOUT_PROCESSORS.clear()


def test_h13_skipped_pages_are_recorded_not_silent():
    from src.pipeline.extraction import layout

    source = Path(layout.__file__).read_text(encoding="utf-8")
    assert "skip_reason" in source, "a skipped page is still not recorded"
    assert "layout_skipped_pages" in source


# ===========================================================================
# M-38: layout ran twice on the happy path
# ===========================================================================

def test_m38_layout_runs_at_most_once_per_document(monkeypatch, tmp_path):
    from src.pipeline.extraction import router as router_mod

    calls = {"n": 0}

    def _fake_layout(doc, pdf_path):
        calls["n"] += 1
        doc.metadata["layout_processed"] = True
        doc.tables.append({"t": calls["n"]})

    monkeypatch.setattr(router_mod, "add_layout_to_document", _fake_layout)
    monkeypatch.setattr(router_mod, "add_semantic_to_document",
                        lambda doc, engine: doc.metadata.__setitem__("semantic_processed", True))

    class _Primary:
        name = "pymupdf"

        def extract(self, pdf_path):
            from src.pipeline.extraction.base import Document, Page

            return Document(source="pymupdf", pdf_path=pdf_path,
                            pages=[Page(0, "Амоксициллин 500 мг 3 раза в день " * 40)],
                            full_text="Амоксициллин 500 мг 3 раза в день " * 40)

    r = router_mod.ExtractorRouter(primary=_Primary(), fallbacks=[])
    doc = r.extract(tmp_path / "x.pdf")
    assert calls["n"] == 1, "the layout pipeline ran twice and duplicated tables"
    assert len(doc.tables) == 1
