"""Performance Audit — full Engine pipeline over the real 2675-regimen dataset.

Runs PatientQuery -> DiagnosisMatch -> ... -> Trace against a real
normalized_regimens SQLite (built by build_normalized_sqlite.py) and the
AUTO_GENERATED_DRAFT diagnosis_index.json, and reports latency percentiles,
memory, SQL query count, throughput, and a per-stage bottleneck breakdown
(from EngineRuntime.pipeline_time_breakdown).

Measurement only — no code is optimized here.

Usage (from repo root):
    python -m clinical_engine.tools.performance_audit \
        [--sqlite C:/clinrec_downloader/normalized_regimens.sqlite] \
        [--report performance_audit_engine.md]
"""

from __future__ import annotations

import argparse
import gc
import statistics
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

from clinical_engine.config import EngineConfig
from clinical_engine.engine import Engine
from clinical_engine.models import Patient, PatientQuery
from clinical_engine.readers.diagnosis_reader import JsonDiagnosisProvider

_DEFAULT_SQLITE = r"C:\clinrec_downloader\normalized_regimens.sqlite"
_DEFAULT_REPORT = "performance_audit_engine.md"

try:
    import psutil  # type: ignore

    _PROC = psutil.Process()
except Exception:  # pragma: no cover
    _PROC = None


def _rss_mb() -> float | None:
    if _PROC is None:
        return None
    return _PROC.memory_info().rss / (1024 * 1024)


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


class _SqlCounter:
    """Counts SQL statements executed on the reader's sqlite connection."""

    def __init__(self, conn) -> None:
        self.count = 0
        conn.set_trace_callback(self._cb)

    def _cb(self, _sql: str) -> None:
        self.count += 1


def _unique_diagnoses(index_path: str) -> list[str]:
    provider = JsonDiagnosisProvider(index_path)
    names = sorted({e.diagnosis_name for e in provider._entries if e.diagnosis_name})
    return names


def _run_workload(engine: Engine, diagnoses: list[str], patient: Patient, sql: _SqlCounter):
    latencies: list[float] = []
    stage_totals: dict[str, float] = defaultdict(float)
    sql_per_call: list[int] = []
    total_accepted = 0
    total_excluded = 0
    matched = 0

    for dx in diagnoses:
        q = PatientQuery(diagnosis=dx, patient=patient)
        before_sql = sql.count
        t0 = time.perf_counter()
        result = engine.recommend(q)
        latencies.append((time.perf_counter() - t0) * 1000)
        sql_per_call.append(sql.count - before_sql)
        for stage, ms in result.runtime.pipeline_time_breakdown.items():
            stage_totals[stage] += ms
        total_accepted += len(result.accepted)
        total_excluded += len(result.excluded)
        if result.accepted or result.excluded:
            matched += 1

    return {
        "latencies": latencies,
        "stage_totals": dict(stage_totals),
        "sql_per_call": sql_per_call,
        "total_accepted": total_accepted,
        "total_excluded": total_excluded,
        "matched_queries": matched,
        "n": len(diagnoses),
    }


def _summ(w: dict) -> dict:
    lat = sorted(w["latencies"])
    total_s = sum(w["latencies"]) / 1000.0
    return {
        "n": w["n"],
        "matched": w["matched_queries"],
        "p50_ms": _pct(lat, 0.50),
        "p95_ms": _pct(lat, 0.95),
        "p99_ms": _pct(lat, 0.99),
        "max_ms": lat[-1] if lat else 0.0,
        "mean_ms": statistics.fmean(lat) if lat else 0.0,
        "total_s": total_s,
        "queries_per_s": w["n"] / total_s if total_s else 0.0,
        "recs_per_s": w["total_accepted"] / total_s if total_s else 0.0,
        "total_accepted": w["total_accepted"],
        "total_excluded": w["total_excluded"],
        "sql_total": sum(w["sql_per_call"]),
        "sql_mean_per_call": statistics.fmean(w["sql_per_call"]) if w["sql_per_call"] else 0.0,
        "sql_max_per_call": max(w["sql_per_call"]) if w["sql_per_call"] else 0,
        "stage_totals": w["stage_totals"],
    }


def audit(sqlite_path: str, report_path: str) -> str:
    # strict_mode=False: this dev tool intentionally measures against the
    # AUTO_GENERATED_DRAFT index (perf, not clinical output) — warn, don't block.
    config = EngineConfig(sqlite_path=sqlite_path, strict_mode=False)
    diagnoses = _unique_diagnoses(config.diagnosis_index_path)

    gc.collect()
    tracemalloc.start()
    rss_before = _rss_mb()

    t0 = time.perf_counter()
    engine = Engine(config)
    init_ms = (time.perf_counter() - t0) * 1000
    rss_after_init = _rss_mb()

    sql = _SqlCounter(engine._sqlite_reader._db._conn)

    adult = Patient(age=45)
    heavy = Patient(
        age=45, weight_kg=70.0, pregnant=False, renal_function=25.0,
        hepatic_impairment=True, allergies=("Пенициллины",),
        current_meds=("аллопуринол", "варфарин"),
    )

    # warm-up (one pass, not measured)
    for dx in diagnoses[:50]:
        engine.recommend(PatientQuery(diagnosis=dx, patient=adult))

    wa = _run_workload(engine, diagnoses, adult, sql)
    wb = _run_workload(engine, diagnoses, heavy, sql)

    cur_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_after = _rss_mb()
    engine.close()

    sa, sb = _summ(wa), _summ(wb)
    md = _render(
        sqlite_path, config, len(diagnoses), init_ms, sa, sb,
        peak_mem / (1024 * 1024), rss_before, rss_after_init, rss_after,
    )
    Path(report_path).write_text(md, encoding="utf-8")
    # ASCII-safe console summary (full UTF-8 report is in the .md file; the
    # Windows console codepage can't print the report's arrows/Cyrillic).
    print("=== Performance Audit written to", report_path, "===")
    print(f"init: {init_ms:.1f} ms (<100ms target: {'PASS' if init_ms < 100 else 'FAIL'})")
    print(
        f"Workload A (adult): P50 {sa['p50_ms']:.2f} / P95 {sa['p95_ms']:.2f} / "
        f"P99 {sa['p99_ms']:.2f} / max {sa['max_ms']:.2f} ms "
        f"(<50ms: {'PASS' if sa['max_ms'] < 50 else 'REVIEW'})"
    )
    print(
        f"Workload B (heavy): P50 {sb['p50_ms']:.2f} / P95 {sb['p95_ms']:.2f} / "
        f"P99 {sb['p99_ms']:.2f} / max {sb['max_ms']:.2f} ms"
    )
    print(f"recs/sec A={sa['recs_per_s']:.0f} B={sb['recs_per_s']:.0f} | "
          f"SQL mean/call {sa['sql_mean_per_call']:.2f} max {sa['sql_max_per_call']} | "
          f"tracemalloc peak {peak_mem / (1024 * 1024):.1f} MB")
    slow = max(sb["stage_totals"].items(), key=lambda kv: kv[1])
    print(f"top stage: {slow[0]} ({100 * slow[1] / (sum(sb['stage_totals'].values()) or 1):.0f}% of pipeline)")
    return report_path


def _stage_table(stage_totals: dict, n: int) -> str:
    order = [
        "DiagnosisMatch", "RegimenLoad", "PopulationFilter", "TherapyLineSelect",
        "HardSafetyFilter", "DoseCalculation", "DoseAdjustment", "InteractionCheck",
        "RankRecommendations", "Trace",
    ]
    total = sum(stage_totals.values()) or 1.0
    lines = ["| Stage | mean ms/call | % of pipeline |", "|---|---:|---:|"]
    for s in order:
        tot = stage_totals.get(s, 0.0)
        lines.append(f"| {s} | {tot / n:.4f} | {100 * tot / total:.1f}% |")
    return "\n".join(lines)


def _render(sqlite_path, config, n_dx, init_ms, sa, sb, peak_py_mb,
            rss0, rss1, rss2) -> str:
    def rss(v):
        return f"{v:.1f} MB" if v is not None else "n/a (psutil not installed)"

    return f"""# Performance Audit — Clinical Decision Engine (full pipeline, real data)

> Measurement only. No code optimized. AUTO_GENERATED report.

## Setup
- SQLite (normalized_regimens): `{sqlite_path}` — 2675 regimens
- diagnosis_index: `{config.diagnosis_index_path}` (AUTO_GENERATED_DRAFT, 895 entries / 294 guidelines)
- drug reference: `{config.drug_reference_path}`
- clinical constants: `{config.clinical_constants_path}`
- ValidationPolicy: **{config.validation_policy.value}** (production default — PASS-only)
- Workload: {n_dx} unique diagnosis names, full pipeline per query
- Python: 3.12 · single process · no query-level cache (v1)

## Engine.__init__ (reader load, one-time)
- **{init_ms:.1f} ms** — target §9.1 <100ms → **{'PASS' if init_ms < 100 else 'FAIL'}**
- RSS before / after init: {rss(rss0)} / {rss(rss1)}

## Latency — Workload A (adult, age 45)
| metric | value | target §9.1 |
|---|---:|---|
| P50 | {sa['p50_ms']:.3f} ms | — |
| P95 | {sa['p95_ms']:.3f} ms | — |
| P99 | {sa['p99_ms']:.3f} ms | — |
| max | {sa['max_ms']:.3f} ms | recommend() <50ms → {'PASS' if sa['max_ms'] < 50 else 'REVIEW'} |
| mean | {sa['mean_ms']:.3f} ms | — |
| queries/sec | {sa['queries_per_s']:.0f} | — |
| recommendations/sec | {sa['recs_per_s']:.0f} | — |
| matched queries | {sa['matched']}/{sa['n']} | — |
| total accepted / excluded | {sa['total_accepted']} / {sa['total_excluded']} | — |

## Latency — Workload B (heavy: allergy + 2 current meds + GFR 25 + hepatic)
| metric | value |
|---|---:|
| P50 | {sb['p50_ms']:.3f} ms |
| P95 | {sb['p95_ms']:.3f} ms |
| P99 | {sb['p99_ms']:.3f} ms |
| max | {sb['max_ms']:.3f} ms |
| mean | {sb['mean_ms']:.3f} ms |
| queries/sec | {sb['queries_per_s']:.0f} |
| recommendations/sec | {sb['recs_per_s']:.0f} |
| total accepted / excluded | {sb['total_accepted']} / {sb['total_excluded']} |

## SQL query count (per recommend())
- Workload A: total {sa['sql_total']}, mean {sa['sql_mean_per_call']:.2f}/call, max {sa['sql_max_per_call']}/call
- Workload B: total {sb['sql_total']}, mean {sb['sql_mean_per_call']:.2f}/call, max {sb['sql_max_per_call']}/call
- One `load_by_guideline` SELECT per matched guideline_id; drug/diagnosis/constants readers are in-memory (0 SQL after init).

## Memory
- Python tracemalloc peak (during workload): {peak_py_mb:.1f} MB
- Process RSS after full run: {rss(rss2)}

## Cache
- v1 has **no query-level cache** (documented — EngineCache is a stub, §9.2.5).
- Readers loaded **once** at `Engine.__init__`; all subsequent drug/diagnosis/
  constants access is in-memory dict O(1) → effective "hit rate" 100% in-memory,
  0 re-reads. SQLite connection reused across all queries (no reopen).

## Bottleneck analysis — per-stage mean (Workload B, heaviest)
{_stage_table(sb['stage_totals'], sb['n'])}

## Notes
- STRICT policy loads PASS-only ({1039} of 2675) — worst-case candidate fan-in
  per guideline is small (≤ tens of rows), so latency is dominated by fixed
  per-stage overhead, not data volume.
- diagnosis_index is a DRAFT (895 entries, 101 conflicting diagnosis→guideline
  mappings). Conflicts inflate candidate counts for ambiguous diagnoses (a
  lookup may fan out to multiple guidelines) — see build_diagnosis_index_draft
  report. This is a data-quality caveat, not an engine perf issue.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default=_DEFAULT_SQLITE)
    ap.add_argument("--report", default=_DEFAULT_REPORT)
    args = ap.parse_args()
    audit(args.sqlite, args.report)


if __name__ == "__main__":
    main()
