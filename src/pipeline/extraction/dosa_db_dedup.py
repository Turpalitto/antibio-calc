"""Deduplicate DOSA-mapped diseases against the existing calculator DB.

Source-prover only. Given a set of newly-mapped disease records (from
``dosa_to_db_mapper``) and the existing calculator recommendations, decide which
mapped records are genuinely NEW nosologies versus which are same-disease /
same-version variants already present. Records judged as duplicates of an
existing entry are DROPPED. A record is never considered "unblockable" here;
this module only decides membership, never calculation status.

Duplicate detection uses two complementary signals:
  * MKB code overlap (any mapped mkb code that also names an existing disease, or
    shares the up-to-4-char block with it).
  * Normalized disease-name token overlap against existing disease names.

A mapped record is dropped as a duplicate if EITHER signal fires. This is
deliberately conservative: an ambiguous record is excluded rather than risk
cluttering the calculator with patient-facing near-duplicates.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_MKB_BLOCK_RE = re.compile(r"^([A-Z][0-9]{0,2})")


def _mkb_block(code: str) -> str:
    """Return the MKB block prefix (e.g. 'J13', 'A69', 'N39') of a code."""
    code = (code or "").strip().upper()
    m = _MKB_BLOCK_RE.match(code)
    return m.group(1) if m else code


def _build_block_index(diseases: Iterable[dict[str, Any]]) -> set[str]:
    blocks: set[str] = set()
    for d in diseases:
        for code in d.get("mkb10", []):
            blocks.add(_mkb_block(code))
    return blocks


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return {t for t in re.split(r"[^0-9а-яёa-z]+", text.lower()) if len(t) >= 4}


def _name_overlap(mapped_name: str, existing_name: str) -> bool:
    """True if the two disease names share >=2 significant tokens."""

    a = _tokenize(mapped_name)
    b = _tokenize(existing_name)
    if not a or not b:
        return False
    shared = a & b
    return len(shared) >= 2


def deduplicate_mapped(
    mapped: Iterable[dict[str, Any]], existing: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Split mapped records into 'new' and 'dropped_duplicate'.

    Returns {new, dropped, existing_block_count}. ``new`` preserves the original
    record objects; ``dropped_duplicate`` is a list of {record, reason}.
    """

    existing_list = list(existing)
    existing_blocks = _build_block_index(existing_list)
    new: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for rec in mapped:
        rec_blocks = {_mkb_block(c) for c in rec.get("mkb10", [])}
        block_hit = bool(rec_blocks & existing_blocks)

        name_hit = False
        for ex in existing_list:
            if _name_overlap(rec.get("name") or "", ex.get("name") or ""):
                name_hit = True
                break

        if block_hit or name_hit:
            reason = "MKB_OVERLAP" if block_hit else "NAME_OVERLAP"
            dropped.append({"record": rec, "reason": reason})
        else:
            new.append(rec)
    return {
        "new": new,
        "dropped": dropped,
        "new_count": len(new),
        "dropped_count": len(dropped),
        "existing_block_count": len(existing_blocks),
    }


def _version_key(rec: dict[str, Any]) -> tuple[int, str]:
    """Sort key preferring the newest guideline version among duplicates."""

    cr_id = str(rec.get("cr_id") or "")
    _, _, ver = cr_id.rpartition("_")
    suffix = re.search(r"(\d+)$", ver)
    return (int(suffix.group(1)) if suffix else 0, cr_id)


def deduplicate_among(new: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Drop cross-version duplicates among the already-new records.

    Two records are grouped together when their significant disease-name token
    set overlaps. Keeps one representative per group (the newest version), so
    a single disease name (e.g. 'Урогенитальный трихомониаз' arriving as 241_1,
    241_2, 241_3) collapses to one record. Returns {kept, dropped_duplicate}.
    """

    records = list(new)
    groups: list[dict[str, Any]] = []
    for rec in records:
        tokens = _tokenize(rec.get("name") or "")
        placed = False
        for grp in groups:
            if tokens & grp["tokens"]:
                grp["members"].append(rec)
                placed = True
                break
        if not placed:
            groups.append({"tokens": tokens, "members": [rec]})

    kept: list[dict[str, Any]] = []
    dropped: dict[str, Any] = {}
    for grp in groups:
        members = grp["members"]
        members.sort(key=_version_key, reverse=True)
        kept.append(members[0])
        for dup in members[1:]:
            dropped[dup.get("id", str(dup))] = {
                "record": dup,
                "reason": "CROSS_VERSION_DUPLICATE",
                "kept": members[0].get("id"),
            }
    return {"kept": kept, "dropped_duplicate": dropped}
