"""RC-030 C5 — consolidated, deterministic owner-review interface builder.

Single source of truth for turning `owner_review_template.html` + a
governed record dataset into a self-contained, offline owner-review HTML
file. Supersedes the earlier separate `build_interface.py` /
`build_control_sample_interface.py` pair (kept on disk, unused, for
history) — one template, one builder, dataset-driven.

Usage:
    python generated/rc030_recovery/build_interface.py \\
        --dataset generated/rc030_recovery/owner_review_data.json \\
        --output generated/rc030_recovery/RC030_OWNER_REVIEW_INTERFACE.html \\
        --mode all

    python generated/rc030_recovery/build_interface.py \\
        --dataset generated/rc030_recovery/owner_control_sample_data.json \\
        --output generated/rc030_recovery/RC030_OWNER_CONTROL_SAMPLE_INTERFACE.html \\
        --mode control --check

Guarantees:
- repository-relative inputs only (paths resolved relative to the
  invoking working directory / explicit CLI args — never a hard-coded
  personal path);
- no network access;
- deterministic output for the same inputs (record order is preserved
  exactly as it appears in the dataset file — the builder never
  reorders records, since curated review order, e.g. the control
  sample's fixed error->table->ambiguous->random sequence, is part of
  the dataset's own governance, not something a build step should
  silently change);
- refuses to build if the dataset is missing required fields, contains
  a duplicate `evidence_hash` (the `unit_id`/`source_packet_hash` used
  by the C4 schema), or omits the template placeholder;
- refuses to embed anything under an `owner_verdict`/`canonical_verdict`
  key in the input dataset (a governed dataset must never pre-load a
  verdict — that is the owner's job, done in-browser, never at build
  time);
- writes only under `generated/` (the two hard-coded relative defaults
  live there; `--output` is not restricted beyond that convention, but
  the caller is responsible for honoring it);
- atomic write (temp file + rename) so a crash mid-write cannot leave a
  half-written HTML file at the final path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE / "owner_review_template.html"
PLACEHOLDER = "__RECORDS_JSON__"
MODE_PLACEHOLDER = "__MODE__"

_FORBIDDEN_PRELOADED_KEYS = ("owner_verdict", "canonical_verdict", "ui_action", "human_fidelity_verdict")

# A real absolute-path leak (C:\clinrec_downloader\...) was found in an
# earlier dataset revision during C5 hardening: every record embedded a
# machine-specific PDF root. The interface now resolves PDFs against an
# owner-configured, localStorage-only root at runtime (never committed) —
# datasets must carry only a bare filename in `source_pdf`, never a path.
_FORBIDDEN_DATA_KEYS = ("pdf_local_path",)
_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]|^/home/|^/Users/")


def _load_dataset(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"dataset not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise SystemExit(f"dataset {path} has no non-empty 'records' array")
    return records


def _validate_records(records: list[dict]) -> None:
    seen_hashes: dict[str, int] = {}
    for i, r in enumerate(records):
        if "evidence_hash" not in r or not r["evidence_hash"]:
            raise SystemExit(f"record {i} (regimen_id={r.get('regimen_id')!r}) is missing evidence_hash")
        h = r["evidence_hash"]
        if h in seen_hashes:
            raise SystemExit(
                f"duplicate evidence_hash {h!r}: records {seen_hashes[h]} and {i} "
                f"(regimen_id={r.get('regimen_id')!r}) — refusing to build"
            )
        seen_hashes[h] = i
        for forbidden in _FORBIDDEN_PRELOADED_KEYS:
            if forbidden in r:
                raise SystemExit(
                    f"record {i} (regimen_id={r.get('regimen_id')!r}) contains forbidden preloaded "
                    f"key {forbidden!r} — a governed dataset must never pre-load a verdict"
                )
        for forbidden in _FORBIDDEN_DATA_KEYS:
            if forbidden in r:
                raise SystemExit(
                    f"record {i} (regimen_id={r.get('regimen_id')!r}) contains forbidden key "
                    f"{forbidden!r} — absolute local PDF paths must never be embedded in a committed "
                    f"dataset; the interface resolves PDFs against an owner-configured local root instead"
                )
        for key, value in r.items():
            if isinstance(value, str) and _ABS_PATH_RE.match(value):
                raise SystemExit(
                    f"record {i} (regimen_id={r.get('regimen_id')!r}) field {key!r} looks like an "
                    f"absolute local filesystem path ({value!r}) — refusing to build"
                )


def build(dataset_path: Path, template_path: Path, output_path: Path, mode: str, check: bool = False) -> str:
    template = template_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"template is missing the {PLACEHOLDER} placeholder — refusing to build a broken file")
    if MODE_PLACEHOLDER not in template:
        raise SystemExit(f"template is missing the {MODE_PLACEHOLDER} placeholder — refusing to build a broken file")

    records = _load_dataset(dataset_path)
    _validate_records(records)

    records_json = json.dumps(records, ensure_ascii=False)
    final = template.replace(PLACEHOLDER, records_json).replace(MODE_PLACEHOLDER, mode)
    content_hash = hashlib.sha256(final.encode("utf-8")).hexdigest()

    if check:
        if not output_path.is_file():
            raise SystemExit(f"--check requested but {output_path} does not exist yet")
        existing = output_path.read_text(encoding="utf-8")
        existing_hash = hashlib.sha256(existing.encode("utf-8")).hexdigest()
        if existing_hash != content_hash:
            raise SystemExit(
                f"--check FAILED: {output_path} does not match a fresh deterministic build "
                f"(existing sha256={existing_hash}, fresh sha256={content_hash})"
            )
        print(f"--check OK: {output_path} matches a fresh deterministic build (sha256={content_hash})")
        return content_hash

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(final, encoding="utf-8")
    os.replace(tmp_path, output_path)  # atomic on both POSIX and Windows NTFS
    print(f"built {output_path} ({len(final)} bytes, {len(records)} records, mode={mode}, sha256={content_hash})")
    return content_hash


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the RC-030 offline owner-review interface from a template + governed dataset.",
    )
    parser.add_argument("--dataset", type=Path, required=True,
                         help="Path to a governed record dataset JSON (repository-relative, e.g. "
                              "generated/rc030_recovery/owner_review_data.json).")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE,
                         help=f"Path to the HTML template (default: {DEFAULT_TEMPLATE}).")
    parser.add_argument("--output", type=Path, required=True,
                         help="Output HTML path (repository-relative).")
    parser.add_argument("--mode", choices=["all", "control", "range-exact-review", "range-single-review"],
                         required=True,
                         help="'all' = full record set, no fixed review order assumed; "
                              "'control' = curated control-sample subset with fixed review order banner; "
                              "'range-exact-review' = RC-030 C6.7 retained-exact-link dose-range confirmation queue; "
                              "'range-single-review' = RC-030 C6.7 single-candidate dose-range review queue "
                              "(never migration-safe regardless of outcome).")
    parser.add_argument("--check", action="store_true",
                         help="Do not write; verify the existing --output file is byte-identical to a "
                              "fresh deterministic build from the current inputs. Exits non-zero on mismatch.")
    args = parser.parse_args(argv)

    build(args.dataset, args.template, args.output, args.mode, check=args.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
