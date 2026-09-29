"""Golden Clinical Cases runner (spec §10.1 Tier 3).

Loads doctor-authored case files, runs the UNMODIFIED Engine over each, and
reports PASS/FAIL per assertion. Read-only harness: it does not modify the
Engine, the Medical Normalizer, or the case files.

A case is a JSON object:
    {
      "id": "...",
      "description": "...",
      "query":   { diagnosis / icd10 / patient{...} / preferences{...} },
      "expect":  { ...assertions, all optional... },
      "provenance": { author / verified_at / source }
    }

Only the assertions present in `expect` are checked. Supported assertions are
listed in ASSERTIONS below and in schema.json. Assertions operate solely on the
public RecommendationSet — no reach into engine internals.

Every assertion evaluates against the ranked, accepted recommendations
(accepted[0] == rank 1) and the excluded list / engine_notes / safety_flags.

Note: `first_candidate_confidence_*` reads `accepted[0].candidate.confidence`
(the real SQLite normalization confidence). Recommendation.confidence (§7.3)
is NOT asserted — it is a documented not-yet-populated field.

M-8: the runner no longer disables the Milestone-13 production guard by
default. Against an AUTO_GENERATED_DRAFT / PARTIALLY_CURATED index the Engine
refuses to start (each case then reports ERROR, which is visible), and a run
against uncurated routing requires an explicit ``--allow-uncurated-index``,
which stamps a warning into the report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from clinical_engine.config import EngineConfig
from clinical_engine.engine import Engine
from clinical_engine.models import (
    EngineError,
    Patient,
    PatientQuery,
    Preferences,
    RecommendationSet,
)

# ── Case model ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class GoldenCase:
    id: str
    description: str
    query: dict[str, Any]
    expect: dict[str, Any]
    provenance: dict[str, Any] = field(default_factory=dict)
    source_file: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any], source_file: str | None = None) -> "GoldenCase":
        return cls(
            id=str(d.get("id") or ""),
            description=str(d.get("description") or ""),
            query=d.get("query") or {},
            expect=d.get("expect") or {},
            provenance=d.get("provenance") or {},
            source_file=source_file,
        )


@dataclass(frozen=True, slots=True)
class AssertionResult:
    name: str
    passed: bool
    expected: Any
    actual: Any
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    description: str
    passed: bool
    assertions: tuple[AssertionResult, ...]
    error: str | None = None  # infrastructure error (EngineError), not a FAIL

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        return "PASS" if self.passed else "FAIL"


# ── Query building ──────────────────────────────────────────


def _build_query(q: dict[str, Any]) -> PatientQuery:
    p = q.get("patient") or {}
    pref = q.get("preferences") or {}
    patient = Patient(
        age=p.get("age"),
        weight_kg=p.get("weight_kg"),
        pregnant=bool(p.get("pregnant", False)),
        renal_function=p.get("renal_function"),
        hepatic_impairment=bool(p.get("hepatic_impairment", False)),
        allergies=tuple(p.get("allergies") or ()),
        current_meds=tuple(p.get("current_meds") or ()),
    )
    preferences = Preferences(
        therapy_line=pref.get("therapy_line"),
        route_preference=pref.get("route_preference"),
        population=pref.get("population"),
    )
    return PatientQuery(
        diagnosis=q.get("diagnosis"),
        icd10=q.get("icd10"),
        patient=patient,
        preferences=preferences,
    )


# ── Assertions ──────────────────────────────────────────────
# Each assertion: (result: RecommendationSet, expected) -> AssertionResult.
# `_first` helpers guard the empty-accepted case explicitly (never crash).


def _accepted_drug_refs(r: RecommendationSet) -> set[str]:
    return {rec.candidate.drug_ref for rec in r.accepted if rec.candidate.drug_ref}


def _excluded_drug_refs(r: RecommendationSet) -> set[str]:
    return {rec.candidate.drug_ref for rec, _ in r.excluded if rec.candidate.drug_ref}


def _first(r: RecommendationSet):
    return r.accepted[0] if r.accepted else None


def _a(name: str, ok: bool, expected: Any, actual: Any, detail: str = "") -> AssertionResult:
    return AssertionResult(name=name, passed=ok, expected=expected, actual=actual, detail=detail)


def _first_field(r, expected, field_path: str, name: str) -> AssertionResult:
    first = _first(r)
    if first is None:
        return _a(name, False, expected, None, "accepted is empty")
    obj = first.candidate
    actual = getattr(obj, field_path)
    return _a(name, actual == expected, expected, actual)


def _assert_first_drug_normalized(r, e):
    return _first_field(r, e, "drug_normalized", "first_drug_normalized")


def _assert_first_drug_ref(r, e):
    return _first_field(r, e, "drug_ref", "first_drug_ref")


def _assert_first_therapy_line(r, e):
    return _first_field(r, e, "therapy_line", "first_therapy_line")


def _assert_first_route(r, e):
    return _first_field(r, e, "route", "first_route")


def _assert_min_accepted(r, e):
    return _a("min_accepted", len(r.accepted) >= e, f">= {e}", len(r.accepted))


def _assert_max_accepted(r, e):
    return _a("max_accepted", len(r.accepted) <= e, f"<= {e}", len(r.accepted))


def _assert_accepted_empty(r, e):
    is_empty = len(r.accepted) == 0
    return _a("accepted_empty", is_empty == bool(e), e, is_empty)


def _assert_excluded_drug_refs(r, e):
    have = _excluded_drug_refs(r)
    missing = [x for x in e if x not in have]
    return _a("excluded_drug_refs", not missing, e, sorted(have),
              "" if not missing else f"missing from excluded: {missing}")


def _assert_not_accepted_drug_refs(r, e):
    have = _accepted_drug_refs(r)
    present = [x for x in e if x in have]
    return _a("not_accepted_drug_refs", not present, e, sorted(have),
              "" if not present else f"unexpectedly accepted: {present}")


def _assert_excluded_reason_contains(r, e):
    ok = any(e in reason for _, reason in r.excluded)
    return _a("excluded_reason_contains", ok, e, [reason for _, reason in r.excluded])


def _assert_engine_note_code(r, e):
    codes = [n.code for n in r.engine_notes]
    return _a("engine_note_code", e in codes, e, codes)


def _assert_guideline_id(r, e):
    gids = {c.candidate.guideline_id for c in r.accepted}
    return _a("guideline_id", e in gids, e, list(gids))


def _assert_not_guideline_id(r, e):
    gids = {c.candidate.guideline_id for c in r.accepted}
    present = e in gids
    return _a("not_guideline_id", not present, e, list(gids),
              "" if not present else f"unexpectedly matched wrong guideline: {e}")


def _assert_trace_code(r, e):
    """Support for B2: check decision trace codes (uses existing traces on RecommendationSet)."""
    traces = getattr(r, 'traces', ()) or ()
    codes = {getattr(t.decision_code, 'name', str(t.decision_code)) for t in traces}
    return _a("trace_code", e in codes, e, list(codes))


def _assert_safety_flag_codes(r, e):
    codes = {f.code for f in r.safety_flags}
    missing = [x for x in e if x not in codes]
    return _a("safety_flag_codes", not missing, e, sorted(codes),
              "" if not missing else f"missing flags: {missing}")


def _assert_first_candidate_confidence_range(r, e):
    first = _first(r)
    if first is None:
        return _a("first_candidate_confidence_range", False, e, None, "accepted is empty")
    lo, hi = e
    val = first.candidate.confidence
    return _a("first_candidate_confidence_range", lo <= val <= hi, f"[{lo}, {hi}]", val)


def _assert_first_outcome(r, e):
    """Rank-1 outcome as labelled by the Trace stage (ACCEPTED/WARNING/EXCLUDED)."""
    first = _first(r)
    if first is None:
        return _a("first_outcome", False, e, None, "accepted is empty")
    actual = first.outcome.value if first.outcome is not None else None
    return _a("first_outcome", actual == e, e, actual)


def _assert_dose_is_patient_specific(r, e):
    """Whether rank-1's dose reflects this patient's organ function.

    C-2/H-5: a dose emitted next to a *_ADJ_UNPARSED flag is not a
    patient-specific dose, and the golden set must be able to say so.
    """
    first = _first(r)
    if first is None or first.dose is None:
        return _a("dose_is_patient_specific", False, e, None, "no dose on accepted[0]")
    actual = first.dose.dose_is_patient_specific
    return _a("dose_is_patient_specific", actual == bool(e), e, actual)


def _assert_safety_flag_actions(r, e):
    """{flag_code: action} for the codes named, e.g. {"RENAL_ADJ_UNPARSED": "avoid_if_possible"}."""
    actual = {f.code: f.action.value for f in r.safety_flags}
    missing = [c for c in e if c not in actual]
    wrong = {c: (e[c], actual[c]) for c in e if c in actual and actual[c] != e[c]}
    ok = not missing and not wrong
    detail = ""
    if missing:
        detail = f"missing flags: {missing}"
    elif wrong:
        detail = f"action mismatch (expected, actual): {wrong}"
    return _a("safety_flag_actions", ok, e, actual, detail)


ASSERTIONS: dict[str, Callable[[RecommendationSet, Any], AssertionResult]] = {
    "first_drug_normalized": _assert_first_drug_normalized,
    "first_drug_ref": _assert_first_drug_ref,
    "first_therapy_line": _assert_first_therapy_line,
    "first_route": _assert_first_route,
    "min_accepted": _assert_min_accepted,
    "max_accepted": _assert_max_accepted,
    "accepted_empty": _assert_accepted_empty,
    "excluded_drug_refs": _assert_excluded_drug_refs,
    "not_accepted_drug_refs": _assert_not_accepted_drug_refs,
    "excluded_reason_contains": _assert_excluded_reason_contains,
    "engine_note_code": _assert_engine_note_code,
    "guideline_id": _assert_guideline_id,
    "not_guideline_id": _assert_not_guideline_id,
    "trace_code": _assert_trace_code,
    "safety_flag_codes": _assert_safety_flag_codes,
    "safety_flag_actions": _assert_safety_flag_actions,
    "first_candidate_confidence_range": _assert_first_candidate_confidence_range,
    "first_outcome": _assert_first_outcome,
    "dose_is_patient_specific": _assert_dose_is_patient_specific,
}


# ── Runner ──────────────────────────────────────────────────


def run_case(engine: Engine, case: GoldenCase) -> CaseResult:
    """Run one case against an Engine. Infrastructure errors are captured as
    ERROR (not FAIL); clinical no-data is a normal empty result and asserted."""
    try:
        result = engine.recommend(_build_query(case.query))
    except EngineError as exc:  # infra error — surface, don't crash the batch
        return CaseResult(case.id, case.description, False, (), error=f"{exc.code.value}: {exc.detail}")

    assertions: list[AssertionResult] = []
    for key, expected in case.expect.items():
        fn = ASSERTIONS.get(key)
        if fn is None:
            assertions.append(_a(key, False, expected, None, "unknown assertion key"))
            continue
        assertions.append(fn(result, expected))

    passed = all(a.passed for a in assertions) and bool(assertions)
    if not case.expect:
        # A case with no assertions is not a pass — it asserts nothing.
        passed = False
        assertions.append(_a("<has_assertions>", False, ">=1 assertion", 0, "case defines no expectations"))
    return CaseResult(case.id, case.description, passed, tuple(assertions))


def load_cases(directory: str | Path) -> list[GoldenCase]:
    """Load case files: *.json, excluding infrastructure (``_*`` and schema.json)."""
    d = Path(directory)
    cases: list[GoldenCase] = []
    for p in sorted(d.glob("*.json")):
        if p.name.startswith("_") or p.name == "schema.json":
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        cases.append(GoldenCase.from_dict(data, source_file=str(p)))
    return cases


def run_directory(config: EngineConfig, directory: str | Path) -> list[CaseResult]:
    cases = load_cases(directory)
    with Engine(config) as engine:
        return [run_case(engine, c) for c in cases]


def summary(results: list[CaseResult]) -> dict[str, int]:
    return {
        "total": len(results),
        "pass": sum(1 for r in results if r.status == "PASS"),
        "fail": sum(1 for r in results if r.status == "FAIL"),
        "error": sum(1 for r in results if r.status == "ERROR"),
    }


def render_markdown(results: list[CaseResult], *, header_notes: tuple[str, ...] = ()) -> str:
    s = summary(results)
    lines = [
        "# Golden Clinical Cases — Report",
        "",
        f"- Total: **{s['total']}** · ✅ PASS **{s['pass']}** · ❌ FAIL **{s['fail']}** · ⚠️ ERROR **{s['error']}**",
        "",
    ]
    if header_notes:
        lines += ["> " + note for note in header_notes] + [""]
    lines += [
        "| Case | Status | Failing assertions |",
        "|---|---|---|",
    ]
    for r in results:
        if r.status == "PASS":
            fails = "—"
        elif r.error:
            fails = f"(infra) {r.error}"
        else:
            fails = "<br>".join(
                f"`{a.name}`: ожидал {a.expected}, получил {a.actual}"
                + (f" ({a.detail})" if a.detail else "")
                for a in r.assertions if not a.passed
            )
        icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}[r.status]
        lines.append(f"| `{r.case_id}` — {r.description} | {icon} {r.status} | {fails} |")
    return "\n".join(lines) + "\n"


# M-8: the golden suite used to hardcode strict_mode=False, which silently ran
# every golden case against an AUTO_GENERATED_DRAFT diagnosis_index — the exact
# condition the Milestone-13 production guard exists to block. A golden case is a
# clinical assertion, so it must not be validated on uncurated routing by
# default; running against one now requires an explicit, recorded opt-in.
_UNCURATED_INDEX_WARNING = (
    "golden cases are running against a NOT physician-curated diagnosis_index "
    "(strict_mode disabled via --allow-uncurated-index): routing in this report "
    "is not clinically validated"
)


def build_config(
    sqlite_path: str,
    *,
    allow_uncurated_index: bool = False,
    use_terminology_binding: bool = True,
) -> EngineConfig:
    """EngineConfig for a golden run. strict_mode defaults to the guard."""
    return EngineConfig(
        sqlite_path=sqlite_path,
        strict_mode=not allow_uncurated_index,
        use_terminology_binding=use_terminology_binding,
    )


def main() -> None:  # pragma: no cover - CLI wrapper
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="normalized_regimens sqlite path")
    ap.add_argument("--cases", default="clinical_engine/golden_cases")
    ap.add_argument("--report", default="golden_cases_report.md")
    ap.add_argument(
        "--allow-uncurated-index", action="store_true",
        help="run even when the diagnosis_index is not physician-curated "
             "(records a warning in the report; use only for routing experiments)",
    )
    args = ap.parse_args()

    notes: tuple[str, ...] = ()
    if args.allow_uncurated_index:
        notes = (_UNCURATED_INDEX_WARNING,)
        print(f"WARNING: {_UNCURATED_INDEX_WARNING}")
    config = build_config(args.sqlite, allow_uncurated_index=args.allow_uncurated_index)
    results = run_directory(config, args.cases)
    Path(args.report).write_text(
        render_markdown(results, header_notes=notes), encoding="utf-8"
    )
    s = summary(results)
    print(f"Golden cases: total {s['total']} | PASS {s['pass']} | FAIL {s['fail']} | ERROR {s['error']}")
    print(f"report: {args.report}")
    if not results:
        print("NOTE: no cases found — a physician must author cases (see golden_cases/README.md).")


if __name__ == "__main__":  # pragma: no cover
    main()
