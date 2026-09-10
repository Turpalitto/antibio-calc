"""Deterministic builder for the calculator ⇄ guideline-corpus crosswalk.

Pure function over two JSON inputs:

* ``db/antibio_db.json`` (the calculator database — ``recommendations[]``)
* ``clinical_engine/resources/diagnosis_index.json`` (``entries[]``)

Output is a plain ``dict`` that serialises byte-identically for identical
inputs (no wall-clock timestamps, no set iteration order, sorted keys). That
property is what makes the committed artifact drift-checkable in CI.

Run as a module to (re)generate the artifact::

    python -m clinical_engine.crosswalk.builder            # check only
    python -m clinical_engine.crosswalk.builder --write    # regenerate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

BUILDER_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALCULATOR_DB = REPO_ROOT / "db" / "antibio_db.json"
DEFAULT_DIAGNOSIS_INDEX = REPO_ROOT / "clinical_engine" / "resources" / "diagnosis_index.json"
DEFAULT_OUTPUT = REPO_ROOT / "clinical_engine" / "resources" / "calculator_crosswalk.json"

PURPOSE = "NAVIGATION_ONLY"
WARNING = (
    "Навигационная связка калькулятора с корпусом клинических рекомендаций. "
    "НЕ одобрение схем, НЕ снятие блокировки расчёта, НЕ вход рекомендательного "
    "контура. Каждая связь выведена по МКБ-10/названию и требует врачебной проверки."
)

# Method -> human confidence. ICD-10 full-code equality is the strongest signal
# available because both sources copy codes from the same rubricator cards.
METHOD_ICD10_EXACT = "ICD10_EXACT"
METHOD_ICD10_BLOCK = "ICD10_BLOCK"
METHOD_TITLE_EXACT = "TITLE_EXACT"
METHOD_PRIORITY = (METHOD_ICD10_EXACT, METHOD_ICD10_BLOCK, METHOD_TITLE_EXACT)
METHOD_CONFIDENCE = {
    METHOD_ICD10_EXACT: "HIGH",
    METHOD_ICD10_BLOCK: "MEDIUM",
    METHOD_TITLE_EXACT: "LOW",
}

_ICD10_RE = re.compile(r"^[A-Z]\d{2}(?:\.\d{1,3})?$")
_ICD10_HEAD_RE = re.compile(r"^([A-Z]\d{2})")
_SPLIT_RE = re.compile(r"[,;]+")
# МКБ-10 block-range notation ("B20-24"). Mirrors
# src/pipeline/extraction/icd10.py::expand_mkb_range; kept local because
# clinical_engine must not import the extraction pipeline package.
_RANGE_RE = re.compile(r"^([A-Z])(\d{2})\s*[-–—]\s*(?:([A-Z])\s*)?(\d{2})$")
# Russian typography that must not survive normalization (ё/е, ё in titles, etc.)
_TITLE_STRIP_RE = re.compile(r"[^0-9a-zа-я\u0401\u0451]+")


class CrosswalkBuildError(RuntimeError):
    """Raised when an input artifact is missing or structurally unusable."""


# ── normalization ───────────────────────────────────────────────────────────


def _expand_range(token: str) -> list[str]:
    """``"B20-24"`` -> ``["B20" ... "B24"]``; anything else is returned as-is."""
    match = _RANGE_RE.match(token)
    if not match:
        return [token]
    start_letter, start, end_letter, end = match.groups()
    if end_letter is not None and end_letter != start_letter:
        return [token]
    low, high = int(start), int(end)
    if high < low:
        return [token]
    return [f"{start_letter}{n:02d}" for n in range(low, high + 1)]


def normalize_icd10_values(values: Iterable[Any]) -> list[str]:
    """Split/expand/validate ICD-10 codes coming from either source.

    The calculator's ``extended_dosa`` layer stores comma-joined code lists in a
    single array element (e.g. ``["C83.5, C91.0, C95.0"]``) and one block range
    (``"B20-24"``); the corpus stores clean arrays. Both shapes collapse to a
    de-duplicated, order-preserving list of uppercase codes. Malformed tokens are
    dropped here — unlike ``src.pipeline.extraction.icd10.normalize_mkb``, which
    stays permissive to preserve source wording.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        if raw is None:
            continue
        for token in _SPLIT_RE.split(str(raw)):
            for candidate in _expand_range(token.strip().upper().replace(" ", "")):
                if not candidate or not _ICD10_RE.match(candidate):
                    continue
                if candidate not in seen:
                    seen.add(candidate)
                    out.append(candidate)
    return out


def icd_block(code: str) -> str | None:
    """3-character ICD-10 block (``G00.1`` -> ``G00``)."""
    match = _ICD10_HEAD_RE.match(code or "")
    return match.group(1) if match else None


def normalize_text(value: Any) -> str:
    """Case/ё/punctuation-insensitive comparison key for Russian titles."""
    text = str(value or "").lower().replace("\u0451", "\u0435")
    tokens = _TITLE_STRIP_RE.split(text)
    return " ".join(t for t in tokens if t).strip()


def _guideline_sort_key(guideline_id: str) -> tuple[int, str]:
    """Numeric ids sort numerically, anything else falls back to the string."""
    return (0, guideline_id.zfill(12)) if guideline_id.isdigit() else (1, guideline_id)


def _group_guidelines_by_title(records: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Title -> guideline ids sharing it.

    Several ids legitimately share one title: they are different revisions and
    years of the same document. Counting titles therefore undercounts the
    corpus, which is why the census is keyed on ``guideline_id``.
    """
    grouped: dict[str, set[str]] = {}
    for record in records:
        key = normalize_text(record.get("guideline_title"))
        if not key:
            continue
        grouped.setdefault(key, set()).add(str(record.get("guideline_id")))
    return grouped


def canonical_json(payload: Any) -> str:
    """Stable serialization used for hashing."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_sha256(payload: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _load_json(path: str | Path, label: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise CrosswalkBuildError(f"{label} not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CrosswalkBuildError(f"{label} is not readable JSON: {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise CrosswalkBuildError(f"{label} must be a JSON object: {p}")
    return data


def _sha256_of_entries(entries: Sequence[Mapping[str, Any]]) -> str:
    """Hash index entries. Non-mapping rows are hashed as ``null`` so a corrupt
    input still produces a stable digest instead of raising inside the hasher
    (the builder reports it separately via ``skipped_index_entries``)."""
    return content_sha256([dict(e) if isinstance(e, Mapping) else None for e in entries])


#: Calculator fields the crosswalk actually reads. Hashing only these (instead
#: of whole records) makes the artifact stable across rebuilds: ``build_db.py``
#: writes ``guideline_links`` back into the database, and that must not look
#: like input drift.
_CALCULATOR_INPUT_FIELDS = ("id", "name", "synonyms", "cr_id", "mkb10")


def _calculator_input_projection(recommendations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in recommendations:
        if not isinstance(rec, Mapping):
            continue
        out.append({field: rec.get(field) for field in _CALCULATOR_INPUT_FIELDS})
    return out


# ── builder ─────────────────────────────────────────────────────────────────


def build_crosswalk(
    calculator_db: Mapping[str, Any],
    diagnosis_index: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the crosswalk artifact from two already-parsed documents."""
    recommendations = calculator_db.get("recommendations")
    if not isinstance(recommendations, list):
        raise CrosswalkBuildError("calculator db must contain recommendations[]")
    entries = diagnosis_index.get("entries")
    if not isinstance(entries, list):
        raise CrosswalkBuildError("diagnosis index must contain entries[]")

    index_by_full: dict[str, list[dict[str, Any]]] = {}
    index_by_block: dict[str, list[dict[str, Any]]] = {}
    index_by_title: dict[str, list[dict[str, Any]]] = {}
    index_records: list[dict[str, Any]] = []
    skipped_entries = 0
    for entry in entries:
        if not isinstance(entry, Mapping):
            skipped_entries += 1
            continue
        normalized = {
            "guideline_id": str(entry.get("guideline_id") or ""),
            "guideline_title": str(entry.get("guideline_title") or ""),
            "guideline_year": entry.get("guideline_year"),
            "guideline_revision_date": entry.get("guideline_revision_date"),
            "diagnosis_name": str(entry.get("diagnosis_name") or ""),
            "codes": normalize_icd10_values(entry.get("icd10_codes") or []),
        }
        if not normalized["guideline_id"]:
            skipped_entries += 1
            continue
        normalized["blocks"] = sorted({b for b in (icd_block(c) for c in normalized["codes"]) if b})
        index_records.append(normalized)
        for code in normalized["codes"]:
            index_by_full.setdefault(code, []).append(normalized)
        for block in normalized["blocks"]:
            index_by_block.setdefault(block, []).append(normalized)
        title_key = normalize_text(normalized["guideline_title"])
        if title_key:
            index_by_title.setdefault(title_key, []).append(normalized)

    links: list[dict[str, Any]] = []
    per_disease: dict[str, list[dict[str, Any]]] = {}
    unmatched_diseases: list[dict[str, Any]] = []

    for disease in recommendations:
        if not isinstance(disease, Mapping):
            continue
        disease_id = str(disease.get("id") or "")
        if not disease_id:
            continue
        codes = normalize_icd10_values(disease.get("mkb10") or [])
        blocks = sorted({b for b in (icd_block(c) for c in codes) if b})

        grouped: dict[str, dict[str, Any]] = {}

        def _merge(matched: list[dict[str, Any]], method: str, matched_codes: Sequence[str]) -> None:
            for hit in matched:
                gid = hit["guideline_id"]
                slot = grouped.get(gid)
                if slot is None:
                    slot = {
                        "guideline_id": gid,
                        "guideline_title": hit["guideline_title"],
                        "method": method,
                        "matched_icd10": sorted(set(matched_codes)),
                        "diagnosis_names": [],
                        "guideline_years": [],
                    }
                    grouped[gid] = slot
                else:
                    # keep the strongest method already recorded
                    if METHOD_PRIORITY.index(method) < METHOD_PRIORITY.index(slot["method"]):
                        slot["method"] = method
                    slot["matched_icd10"] = sorted(set(slot["matched_icd10"]) | set(matched_codes))
                name = hit["diagnosis_name"].strip()
                if name and name not in slot["diagnosis_names"]:
                    slot["diagnosis_names"].append(name)
                year = hit["guideline_year"]
                if isinstance(year, int) and year not in slot["guideline_years"]:
                    slot["guideline_years"].append(year)

        for code in codes:
            _merge(index_by_full.get(code, []), METHOD_ICD10_EXACT, [code])
        for block in blocks:
            _merge(index_by_block.get(block, []), METHOD_ICD10_BLOCK, [block])

        for title in [disease.get("name"), *(disease.get("synonyms") or [])]:
            key = normalize_text(title)
            if key:
                _merge(index_by_title.get(key, []), METHOD_TITLE_EXACT, [])

        disease_links = sorted(grouped.values(), key=lambda item: (item["guideline_id"],))
        for slot in disease_links:
            slot["confidence"] = METHOD_CONFIDENCE[slot["method"]]
            slot["diagnosis_names"] = sorted(slot["diagnosis_names"])[:8]
            slot["guideline_years"] = sorted(slot["guideline_years"])
            link = {
                "disease_id": disease_id,
                "disease_name": str(disease.get("name") or ""),
                "cr_id": str(disease.get("cr_id") or ""),
                "guideline_id": slot["guideline_id"],
                "guideline_title": slot["guideline_title"],
                "guideline_years": slot["guideline_years"],
                "method": slot["method"],
                "confidence": slot["confidence"],
                "matched_icd10": slot["matched_icd10"],
                "diagnosis_names": slot["diagnosis_names"],
            }
            links.append(link)
        per_disease[disease_id] = disease_links
        if not disease_links:
            unmatched_diseases.append(
                {
                    "disease_id": disease_id,
                    "disease_name": str(disease.get("name") or ""),
                    "cr_id": str(disease.get("cr_id") or ""),
                    "mkb10": codes,
                    "reason": "NO_CORPUS_ENTRY_FOR_ICD10_OR_TITLE",
                }
            )

    linked_guidelines = sorted({link["guideline_id"] for link in links})
    by_guideline = {
        gid: sorted({link["disease_id"] for link in links if link["guideline_id"] == gid})
        for gid in linked_guidelines
    }
    method_counts = {m: sum(1 for link in links if link["method"] == m) for m in METHOD_PRIORITY}

    # Corpus catalogue keyed by guideline_id — the identity that actually
    # matters. One title can be shared by several ids (different revisions and
    # years of the same document), so titles must never be used as the census.
    corpus: dict[str, dict[str, Any]] = {}
    for normalized in index_records:
        gid = normalized["guideline_id"]
        record = corpus.setdefault(
            gid,
            {"guideline_id": gid, "guideline_title": normalized["guideline_title"], "years": set()},
        )
        if not record["guideline_title"] and normalized["guideline_title"]:
            record["guideline_title"] = normalized["guideline_title"]
        if normalized["guideline_year"] is not None:
            record["years"].add(normalized["guideline_year"])

    # Mirror coverage: which corpus guidelines no calculator disease reaches.
    # Deliberately part of the hashed content, so drift detection covers it.
    unlinked_guidelines = [
        {
            "guideline_id": gid,
            "guideline_title": record["guideline_title"],
            "years": sorted(y for y in record["years"] if isinstance(y, int)),
            "reason": "NO_CALCULATOR_DISEASE_MATCHES_ICD10_OR_TITLE",
        }
        for gid, record in sorted(corpus.items(), key=lambda kv: _guideline_sort_key(kv[0]))
        if gid not in by_guideline
    ]

    crosswalk: dict[str, Any] = {
        "links": links,
        "by_guideline": by_guideline,
        "unmatched_diseases": unmatched_diseases,
        "unlinked_guidelines": unlinked_guidelines,
    }
    digest = content_sha256(crosswalk)

    meta: dict[str, Any] = {
        "artifact_type": "CALCULATOR_GUIDELINE_CROSSWALK",
        "schema_version": SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "purpose": PURPOSE,
        "warning": WARNING,
        "id_namespace_note": (
            "calculator cr_id = Минздрав рубрикатор (например 858_1); "
            "corpus guideline_id = внутренний id metadata.sqlite (например 1269). "
            "Пространства имён НЕ пересекаются — соединение только по МКБ-10/названию."
        ),
        "sources": {
            "calculator_db": "db/antibio_db.json",
            "diagnosis_index": "clinical_engine/resources/diagnosis_index.json",
        },
        "inputs_sha256": {
            "calculator_fields": list(_CALCULATOR_INPUT_FIELDS),
            "calculator_recommendations": content_sha256(_calculator_input_projection(recommendations)),
            "diagnosis_index_entries": _sha256_of_entries(entries),
        },
        "diagnosis_index_status": (diagnosis_index.get("meta") or {}).get("status"),
        "methods": list(METHOD_PRIORITY),
        "confidence_by_method": dict(METHOD_CONFIDENCE),
        "coverage": {
            "calculator_diseases": len(per_disease),
            "linked_diseases": sum(1 for links_ in per_disease.values() if links_),
            "unmatched_diseases": len(unmatched_diseases),
            "corpus_guidelines": len(corpus),
            "corpus_titles": len(index_by_title),
            "titles_shared_by_several_guidelines": sum(
                1 for gids in _group_guidelines_by_title(index_records).values() if len(gids) > 1
            ),
            "linked_guidelines": len(linked_guidelines),
            "unlinked_guidelines": len(unlinked_guidelines),
            "links": len(links),
            "links_by_method": method_counts,
            "skipped_index_entries": skipped_entries,
        },
    }
    crosswalk["meta"] = meta
    crosswalk["content_sha256"] = digest
    return crosswalk


def build_crosswalk_from_paths(
    calculator_db_path: str | Path = DEFAULT_CALCULATOR_DB,
    diagnosis_index_path: str | Path = DEFAULT_DIAGNOSIS_INDEX,
) -> dict[str, Any]:
    calculator_db = _load_json(calculator_db_path, "calculator db")
    diagnosis_index = _load_json(diagnosis_index_path, "diagnosis index")
    return build_crosswalk(calculator_db, diagnosis_index)


def write_crosswalk(
    crosswalk: Mapping[str, Any],
    output_path: str | Path = DEFAULT_OUTPUT,
) -> Path:
    """Write the artifact as pretty, sorted, LF JSON with a trailing newline."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(crosswalk, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path


def compact_links(crosswalk: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Per-disease projection small enough to embed into the calculator build.

    Drops ``diagnosis_names`` (the bulky review field, kept in the artifact) and
    renames keys to the short calculator shape. Deterministic ordering.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for link in crosswalk.get("links", ()):
        out.setdefault(str(link.get("disease_id")), []).append(
            {
                "guideline_id": str(link.get("guideline_id") or ""),
                "title": str(link.get("guideline_title") or ""),
                "years": list(link.get("guideline_years") or ()),
                "method": str(link.get("method") or ""),
                "codes": list(link.get("matched_icd10") or ()),
            }
        )
    for links in out.values():
        links.sort(key=lambda item: (item["guideline_id"], item["method"], item["title"]))
    return dict(sorted(out.items()))


def crosswalk_summary(crosswalk: Mapping[str, Any]) -> dict[str, Any]:
    """Metadata block embedded into ``db/antibio_db.json`` alongside the links."""
    meta = crosswalk.get("meta") or {}
    coverage = meta.get("coverage") or {}
    return {
        "purpose": str(meta.get("purpose") or ""),
        "warning": str(meta.get("warning") or ""),
        "schema_version": str(meta.get("schema_version") or ""),
        "builder_version": str(meta.get("builder_version") or ""),
        "content_sha256": str(crosswalk.get("content_sha256") or ""),
        "diagnosis_index_status": meta.get("diagnosis_index_status"),
        "links": coverage.get("links"),
        "linked_diseases": coverage.get("linked_diseases"),
        "calculator_diseases": coverage.get("calculator_diseases"),
        "linked_guidelines": coverage.get("linked_guidelines"),
        "unmatched_diseases": coverage.get("unmatched_diseases"),
        "links_by_method": coverage.get("links_by_method"),
        "confidence_by_method": meta.get("confidence_by_method"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify the calculator ⇄ guideline-corpus crosswalk"
    )
    parser.add_argument("--calculator-db", default=str(DEFAULT_CALCULATOR_DB))
    parser.add_argument("--diagnosis-index", default=str(DEFAULT_DIAGNOSIS_INDEX))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the artifact (default: verify the committed artifact is in sync)",
    )
    args = parser.parse_args(argv)

    crosswalk = build_crosswalk_from_paths(args.calculator_db, args.diagnosis_index)
    out = Path(args.out)

    if args.write:
        write_crosswalk(crosswalk, out)
        coverage = crosswalk["meta"]["coverage"]
        print(
            json.dumps(
                {"written": str(out), "content_sha256": crosswalk["content_sha256"], "coverage": coverage},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    if not out.is_file():
        print(f"CROSSWALK_MISSING: {out} — run `python -m clinical_engine.crosswalk.builder --write`")
        return 2
    expected = json.dumps(crosswalk, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    actual = out.read_text(encoding="utf-8")
    if actual != expected:
        print(
            "CROSSWALK_DRIFT: committed artifact does not match its inputs — "
            "run `python -m clinical_engine.crosswalk.builder --write`"
        )
        return 1
    print(json.dumps({"in_sync": str(out), "content_sha256": crosswalk["content_sha256"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
