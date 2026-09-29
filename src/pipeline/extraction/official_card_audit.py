"""Capture reproducible official Minzdrav clinical-guideline card metadata.

This artifact verifies source identity and current rubricator status only.  It
does not approve regimens or make extracted doses calculation-ready.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import urlopen

# L-16: one API, two HTTP stacks.  `httpx` was imported INSIDE two functions while
# `fetch_card` used `urllib.request`, so there was no shared retry policy, no
# shared timeout default and no shared connection pool.  httpx is now imported once
# at module level; the single `fetch_card` urlopen call is kept explicit for
# callers that inject their own `opener` (tests do).
import httpx


API_ROOT = "https://apicr.minzdrav.gov.ru/api.ashx"

# M-15: `while len(records) < total` with no page guard is an unbounded loop if
# TotalRecords is wrong, and returned page 1 only when TotalRecords was absent.
MAX_REGISTRY_PAGES = 200


def _card_sort_key(value: str) -> tuple:
    """Numeric-aware sort key that never raises on a non-numeric id.

    M-14: ``tuple(int(p) for p in value.split("_"))`` raised ValueError on ids like
    "КР-314_3" -- and it did so INSIDE the sort, i.e. after every HTTP request had
    already been paid for, discarding the whole artifact.
    """
    parts = []
    for chunk in str(value).replace("-", "_").split("_"):
        try:
            parts.append((0, int(chunk), ""))
        except ValueError:
            parts.append((1, 0, chunk))
    return tuple(parts)


def candidate_card_ids(inventory: Mapping[str, Any]) -> list[str]:
    """Return unique best-known rubricator revisions from an inventory."""
    result: set[str] = set()
    for row in inventory.get("rows", []):
        metadata = row.get("latest_local_metadata") or {}
        card_id = metadata.get("CodeVersion") or row.get("declared_cr_id")
        card_id = str(card_id or "").strip()
        if card_id and card_id != "\u2014":
            result.add(card_id)
    return sorted(result, key=_card_sort_key)


def fetch_card(card_id: str, *, opener: Callable[..., Any] = urlopen) -> dict[str, Any]:
    query = urlencode({"op": "GetClinrec2", "id": card_id, "ssid": ""})
    with opener(f"{API_ROOT}?{query}", timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    if not isinstance(payload, dict) or not payload.get("id"):
        raise ValueError(f"rubricator returned no card for {card_id}")
    return payload


def fetch_current_registry(*, opener: Callable[..., Any] = urlopen) -> list[dict[str, Any]]:
    """Fetch the official list of all currently published rubricator cards."""
    body: dict[str, Any] = {
        "filters": [{
            "fieldName": "status", "filterType": 1, "filterValueType": 2,
            "value1": 0, "value2": "", "values": [],
        }],
        "sortOption": {"fieldName": "publishdate", "sortType": 2},
        "pageSize": 100,
        "currentPage": 1,
        "useANDoperator": True,
        "columns": [],
    }
    records: list[dict[str, Any]] = []
    total: int | None = None
    page_number = 1
    while page_number <= MAX_REGISTRY_PAGES:
        response = httpx.post(
            f"{API_ROOT}?op=GetJsonClinrecsFilterV2", json=body, timeout=30
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("Data")
        if not isinstance(page, list):
            raise ValueError("rubricator registry response has no Data list")
        if total is None:
            # M-15: `TotalRecords` was coerced with `or len(page)`, so an ABSENT
            # count made the loop exit after page 1 and the audit silently covered
            # 100 of ~2000 guidelines.  When it is absent we page until a short
            # page proves we reached the end.
            raw_total = payload.get("TotalRecords")
            total = int(raw_total) if raw_total not in (None, "") else None
        records.extend(page)
        if not page or (total is not None and len(records) >= total):
            break
        if total is None and len(page) < int(body["pageSize"]):
            break
        body["currentPage"] = page_number = page_number + 1
    if page_number > MAX_REGISTRY_PAGES:
        raise RuntimeError(
            f"rubricator registry did not terminate within {MAX_REGISTRY_PAGES} pages"
        )
    return records


def compact_registry_card(payload: Mapping[str, Any]) -> dict[str, Any]:
    card_id = str(payload.get("CodeVersion") or "")
    return {
        "id": card_id,
        "code": payload.get("Code"),
        "version": payload.get("Version"),
        "name": payload.get("Name"),
        "status": payload.get("Status"),
        "apply_status_calculated": payload.get("ApplyStatusCalculated"),
        # L-17: `applicable_count` reads this key, but the registry payload may not
        # carry it -- the count came out 0 with nothing to explain it.  Absence is
        # now explicit in the artifact.
        "apply_status_calculated_present": "ApplyStatusCalculated" in payload,
        "publish_date": payload.get("PublishDateStr"),
        "created": payload.get("CreatedStr"),
        "age_category": payload.get("AgeCategoryStr"),
        "mkbs": [
            item.get("MkbCode") if isinstance(item, Mapping) else item
            for item in (payload.get("Mkbs") or [])
        ],
        "prev_cr_id": payload.get("PrevCrId"),
        "npc_approved": payload.get("NPC_approved"),
        "source_url": f"https://cr.minzdrav.gov.ru/view-cr/{card_id}",
    }


def fetch_current_registry_card(card_id: str) -> dict[str, Any]:
    """Fetch one exact current card from the compact official registry API."""
    body = {
        "filters": [
            {"fieldName": "status", "filterType": 1, "filterValueType": 2,
             "value1": 0, "value2": "", "values": []},
            {"fieldName": "codeversion", "filterType": 1, "filterValueType": 2,
             "value1": card_id, "value2": "", "values": []},
        ],
        "sortOption": {"fieldName": "publishdate", "sortType": 2},
        "pageSize": 10,
        "currentPage": 1,
        "useANDoperator": True,
        "columns": [],
    }
    response = httpx.post(
        f"{API_ROOT}?op=GetJsonClinrecsFilterV2", json=body, timeout=30
    )
    response.raise_for_status()
    records = response.json().get("Data") or []
    exact = [item for item in records if str(item.get("CodeVersion")) == card_id]
    if len(exact) != 1:
        raise ValueError(f"exact current registry card count for {card_id}: {len(exact)}")
    return exact[0]


def build_exact_registry_audit(
    inventory: Mapping[str, Any],
    *,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_current_registry_card,
    captured_at: str | None = None,
    max_workers: int = 6,
) -> dict[str, Any]:
    requested_ids = candidate_card_ids(inventory)
    cards: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        pending = {executor.submit(fetcher, card_id): card_id for card_id in requested_ids}
        for future in as_completed(pending):
            card_id = pending[future]
            try:
                card = compact_registry_card(future.result())
                card["requested_id"] = card_id
                card["revision_changed"] = False
                cards.append(card)
            except Exception as exc:
                failures.append({"requested_id": card_id, "error": str(exc)})
    cards.sort(key=lambda card: _card_sort_key(card["id"]))
    failures.sort(key=lambda item: _card_sort_key(item["requested_id"]))
    return {
        "artifact_type": "OFFICIAL_RUBRICATOR_CARD_AUDIT",
        "schema_version": "1.2.0",
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
        "api_root": API_ROOT,
        "lookup_mode": "EXACT_CURRENT_REGISTRY_CARD",
        "requested_count": len(requested_ids),
        "verified_count": len(cards),
        "applicable_count": sum(card.get("apply_status_calculated") == 1 for card in cards),
        "applicable_count_computable": all(
            card.get("apply_status_calculated_present") for card in cards
        ) if cards else False,
        "revision_change_count": 0,
        "cards": cards,
        "failures": failures,
        "warning": "Card status is source identity evidence, not clinical dose approval.",
    }


def build_registry_audit(
    inventory: Mapping[str, Any],
    *,
    registry_fetcher: Callable[[], list[Mapping[str, Any]]] = fetch_current_registry,
    captured_at: str | None = None,
) -> dict[str, Any]:
    requested_ids = candidate_card_ids(inventory)
    registry = registry_fetcher()
    by_code = {int(item["Code"]): item for item in registry if item.get("Code") is not None}
    cards: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for requested_id in requested_ids:
        try:
            code = int(requested_id.split("_", 1)[0])
        except (TypeError, ValueError):
            # M-14: a non-numeric code prefix must become a recorded failure, not
            # an exception that discards every card already fetched.
            failures.append({
                "requested_id": requested_id,
                "error": f"non-numeric code prefix in {requested_id!r}",
            })
            continue
        payload = by_code.get(code)
        if payload is None:
            failures.append({"requested_id": requested_id, "error": "code absent from current registry"})
            continue
        card = compact_registry_card(payload)
        card["requested_id"] = requested_id
        card["revision_changed"] = card["id"] != requested_id
        cards.append(card)
    cards.sort(key=lambda card: _card_sort_key(card["id"]))
    return {
        "artifact_type": "OFFICIAL_RUBRICATOR_CARD_AUDIT",
        "schema_version": "1.1.0",
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
        "api_root": API_ROOT,
        "registry_record_count": len(registry),
        "requested_count": len(requested_ids),
        "verified_count": len(cards),
        "applicable_count": sum(card.get("apply_status_calculated") == 1 for card in cards),
        "applicable_count_computable": all(
            card.get("apply_status_calculated_present") for card in cards
        ) if cards else False,
        "revision_change_count": sum(bool(card["revision_changed"]) for card in cards),
        "cards": cards,
        "failures": failures,
        "warning": "Card status is source identity evidence, not clinical dose approval.",
    }


def compact_card(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep auditable card metadata while excluding large guideline HTML."""
    return {
        "id": str(payload.get("id") or ""),
        "code": payload.get("code"),
        "version": payload.get("version"),
        "name": payload.get("name"),
        "status": payload.get("status"),
        "apply_status": payload.get("apply_status"),
        "apply_status_calculated": payload.get("apply_status_calculated"),
        "publish_date": payload.get("publish_date"),
        "created": payload.get("created"),
        "adult": payload.get("adult"),
        "child": payload.get("child"),
        "mkb": payload.get("mkb"),
        "mkbs": payload.get("mkbs") or [],
        "prev_cr_id": payload.get("prev_cr_id"),
        "npc_approved": payload.get("NPC_approved"),
        "source_url": f"https://cr.minzdrav.gov.ru/view-cr/{payload.get('id')}",
    }


def build_audit(
    inventory: Mapping[str, Any],
    *,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_card,
    captured_at: str | None = None,
    max_workers: int = 8,
) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    card_ids = candidate_card_ids(inventory)
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        pending = {executor.submit(fetcher, card_id): card_id for card_id in card_ids}
        for future in as_completed(pending):
            card_id = pending[future]
            try:
                cards.append(compact_card(future.result()))
            except Exception as exc:  # network/source failures belong in artifact
                failures.append({"requested_id": card_id, "error": str(exc)})
    cards.sort(key=lambda card: _card_sort_key(card["id"]))
    failures.sort(key=lambda item: _card_sort_key(item["requested_id"]))
    return {
        "artifact_type": "OFFICIAL_RUBRICATOR_CARD_AUDIT",
        "schema_version": "1.0.0",
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
        "api_root": API_ROOT,
        "requested_count": len(cards) + len(failures),
        "verified_count": len(cards),
        "applicable_count": sum(
            card.get("apply_status") == "Применяется" and card.get("apply_status_calculated") == 1
            for card in cards
        ),
        "applicable_count_computable": all(
            card.get("apply_status") is not None for card in cards
        ) if cards else False,
        "cards": cards,
        "failures": failures,
        "warning": "Card status is source identity evidence, not clinical dose approval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit official Minzdrav rubricator cards")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--registry-stdin", action="store_true")
    args = parser.parse_args()
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    if args.registry_stdin:
        # The offline path is necessarily the weaker code-only matcher, so the
        # artifact must SAY that rather than looking equivalent.
        registry = json.load(sys.stdin)
        if isinstance(registry, dict):
            registry = registry.get("Data")
        if not isinstance(registry, list):
            raise ValueError("registry stdin must be a JSON list or a response with Data")
        artifact = build_registry_audit(inventory, registry_fetcher=lambda: registry)
    else:
        # M-13: main() used build_registry_audit, which matches on `code` ONLY and
        # ignores the version.  A guideline revised v3 -> v4 was therefore bound to
        # the v4 card while the local PDF was still v3, and the artifact recorded
        # `revision_changed: True` without anything acting on it.  The default is
        # now the EXACT matcher, which fetches the card for the precise code_version
        # and raises when it is not uniquely present.
        artifact = build_exact_registry_audit(inventory)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "requested": artifact["requested_count"],
        "verified": artifact["verified_count"],
        "applicable": artifact["applicable_count"],
        "failures": len(artifact["failures"]),
    }, ensure_ascii=False))
    return 0 if not artifact["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
