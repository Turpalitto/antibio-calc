"""Fetch an official Minzdrav guideline PDF by CodeVersion and verify its pin.

This is a source-integrity bridge, not an approval.  Given a candidate source
spec whose ``guideline_id`` is a rubricator CodeVersion (e.g. ``314_3``), it
downloads the official PDF, validates the ``%PDF`` magic, recomputes the sha256
and compares it against the spec's ``expected_pdf_sha256`` pin.  It never marks
any regimen calculation-ready; it only verifies that the fetched bytes match
the pinned official digest.

The download uses :class:`ClinrecApi` from ``src.pipeline.api_client`` (the same
client that the DOSA/clinrec-downloader pipeline uses), so the fetch-and-verify
bridge works for any future source spec without duplicating URL/retry logic.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from .regimen_candidates import GuidelineCandidateSpec, load_candidate_spec, sha256_file


# Default downloader: awaits ClinrecApi.download_pdf(code_version, dest).
# Injectable so offline/unit tests can supply a fake without touching the network.
AsyncDownloader = Callable[[str, Path], Awaitable[tuple[bool, str, str]]]


def _new_default_downloader() -> tuple[Any, AsyncDownloader]:
    """Return (client, downloader) using the project's shared api_client.

    The client is returned so callers can ``await client.close()`` after use.
    """
    from src.pipeline.api_client import ClinrecApi

    client = ClinrecApi()

    async def downloader(code_version: str, dest_path: Path) -> tuple[bool, str, str]:
        return await client.download_pdf(code_version, dest_path)

    return client, downloader


async def fetch_and_verify_spec(
    spec: GuidelineCandidateSpec,
    *,
    outdir: str | Path,
    downloader: AsyncDownloader,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Download the official PDF for ``spec`` and verify it against the pin.

    Returns a report dict (fail-closed): if the downloaded bytes are not a PDF
    or the sha256 does not match ``expected_pdf_sha256``, the report records the
    mismatch and nothing is treated as verified.  Never approves regimens.
    """
    import hashlib

    code_version = spec.guideline_id
    destination = Path(outdir) / f"CR_{code_version}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)

    ok, downloaded_sha256, errmsg = await downloader(code_version, destination)
    if ok and not destination.exists():
        ok = False
        errmsg = "downloader reported success but wrote no file"

    report: dict[str, Any] = {
        "artifact_type": "SOURCE_PDF_FETCH_VERIFY",
        "schema_version": "1.0.0",
        "captured_at": captured_at,
        "guideline_id": code_version,
        "guideline_title": spec.guideline_title,
        "target": str(destination),
        "downloaded_sha256": downloaded_sha256,
        "expected_pdf_sha256": spec.expected_pdf_sha256,
        "pdf_ok": ok,
        "error": errmsg or "",
        "sha256_match": False,
        "verified": False,
        "size": 0,
    }

    if not ok:
        return report

    report["size"] = destination.stat().st_size
    actual = sha256_file(destination)
    report["downloaded_sha256"] = actual
    match = (
        bool(spec.expected_pdf_sha256)
        and actual.lower() == spec.expected_pdf_sha256.lower()
    )
    report["sha256_match"] = match
    report["verified"] = match and dest_magic_is_pdf(destination)

    return report


def dest_magic_is_pdf(path: Path) -> bool:
    """True only if the file/buffer begins with the ``%PDF`` magic."""
    with path.open("rb") as handle:
        return handle.read(4) == b"%PDF"


def verify_local_pdf(
    spec: GuidelineCandidateSpec,
    *,
    pdf_path: str | Path,
) -> dict[str, Any]:
    """Offline mode: verify an existing local PDF against the spec's pin."""
    path = Path(pdf_path).resolve()
    actual = sha256_file(path)
    match = (
        bool(spec.expected_pdf_sha256)
        and actual.lower() == spec.expected_pdf_sha256.lower()
    )
    dead_pin = not bool(spec.expected_pdf_sha256)
    return {
        "artifact_type": "SOURCE_PDF_LOCAL_VERIFY",
        "schema_version": "1.0.0",
        "guideline_id": spec.guideline_id,
        "guideline_title": spec.guideline_title,
        "local_path": str(path),
        "expected_pdf_sha256": spec.expected_pdf_sha256,
        "actual_pdf_sha256": actual,
        "pin_absent": dead_pin,
        "pdf_magic": dest_magic_is_pdf(path),
        "sha256_match": match,
        "verified": bool(spec.expected_pdf_sha256) and match and dest_magic_is_pdf(path),
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and pin-verify an official Minzdrav guideline PDF"
    )
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--local-pdf", type=Path, dest="local_pdf")
    parser.add_argument("--captured-at", dest="captured_at", default=None)
    args = parser.parse_args(argv)

    spec = load_candidate_spec(args.spec)

    if args.local_pdf is not None:
        report = verify_local_pdf(spec, pdf_path=args.local_pdf)
    else:
        import asyncio

        client, downloader = _new_default_downloader()
        try:
            report = asyncio.run(fetch_and_verify_spec(
                spec,
                outdir=args.outdir or args.output.parent,
                downloader=downloader,
                captured_at=args.captured_at,
            ))
        finally:
            import asyncio as _asyncio

            try:
                _asyncio.get_event_loop().run_until_complete(client.close())
            except RuntimeError:
                pass

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("verified") else 1


__all__ = [
    "fetch_and_verify_spec",
    "verify_local_pdf",
    "dest_magic_is_pdf",
    "load_candidate_spec",
    "GuidelineCandidateSpec",
]


if __name__ == "__main__":
    raise SystemExit(_main())
