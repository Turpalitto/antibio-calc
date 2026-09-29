"""Single, cross-platform build entry point for `antibiotic_calc.html`.

This module is the *only* build script. The Windows-only PowerShell duplicate
(`build_html.ps1`) was deleted: it used a hardcoded `db\\` separator, read the DB
without BOM handling, skipped template validation, and could not reproduce the
committed artifact byte-for-byte.

Build pipeline
  1. run `node db/validate_db.js` and fail the build on any blocking error
     (a missing `node` executable or a missing validator is a hard failure, never
     a silent skip — an unvalidated DB must not reach a physician's screen);
  2. parse `db/antibio_db.json` (UTF-8, BOM tolerant) and check its shape;
  3. read `antibiotic_calc.html.template` (UTF-8) and require exactly one
     `__DB_PLACEHOLDER__` marker;
  4. assert the payload cannot break out of its `<script>` element;
  5. substitute the optional `__BUILD_STAMP__` marker (a no-op when the template
     does not define it, so the template is not coupled to this script);
  6. write the artifact atomically (temp file + `os.replace`) so a failed or
     interrupted build can never leave a half-written clinical document behind;
  7. print the build stamp and the sha256 of the output, so artifact drift
     between machines is detectable.

Usage
    python db/build_html.py                 # validate + build + report hashes
    python db/build_html.py --skip-validate # local iteration only
    python db/build_html.py --node /path/to/node
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "antibio_db.json"
TEMPLATE_PATH = PROJECT_ROOT / "antibiotic_calc.html.template"
OUTPUT_PATH = PROJECT_ROOT / "antibiotic_calc.html"
VALIDATOR_PATH = PROJECT_ROOT / "db" / "validate_db.js"
PLACEHOLDER = "__DB_PLACEHOLDER__"
STAMP_PLACEHOLDER = "__BUILD_STAMP__"
REQUIRED_DB_KEYS = ("meta", "drugs_reference", "categories", "recommendations")
SCRIPT_CLOSE_RE = "</script"


class BuildError(RuntimeError):
    """Raised when the build must not produce an artifact."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_stamp(db_text: str, template_text: str) -> str:
    """Deterministic, machine-independent build identifier.

    Derived from the *inputs* only (never from wall-clock time), so two machines
    building the same inputs produce the same artifact. `ANTIBIO_BUILD_STAMP` can
    override it for a release label.
    """
    override = os.environ.get("ANTIBIO_BUILD_STAMP")
    if override:
        return override
    return "db:%s+tpl:%s" % (
        _sha256_text(db_text)[:12],
        _sha256_text(template_text)[:12],
    )


def _run_validate(node_exe: str | None = None) -> str:
    """Run `node db/validate_db.js`; raise BuildError unless it fully passes.

    Absence is loud on purpose: `node` not installed, or the validator missing,
    both mean the DB is being embedded unvalidated. That is a build failure, not
    a warning.
    """
    if not VALIDATOR_PATH.is_file():
        raise BuildError(
            "db/validate_db.js is missing (%s); refusing to embed an unvalidated "
            "clinical database" % VALIDATOR_PATH
        )
    exe = node_exe or "node"
    if shutil.which(exe) is None and not Path(exe).is_file():
        raise BuildError(
            "Node.js executable %r not found. It is required to run %s; install "
            "Node.js or pass --node /path/to/node" % (exe, VALIDATOR_PATH)
        )
    proc = subprocess.run(
        [exe, str(VALIDATOR_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    report = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        raise BuildError(
            "db/validate_db.js reported blocking errors (exit %d):\n%s"
            % (proc.returncode, report)
        )
    return report


def _load_db(db_path: Path) -> str:
    """Return the DB payload text, checking encoding, JSON validity and shape."""
    raw_bytes = db_path.read_bytes()
    try:
        db_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BuildError("%s is not valid UTF-8: %s" % (db_path, exc)) from exc
    db_text = db_text.strip()
    try:
        parsed = json.loads(db_text)
    except json.JSONDecodeError as exc:
        raise BuildError("%s is not valid JSON: %s" % (db_path, exc)) from exc
    if not isinstance(parsed, dict):
        raise BuildError("%s must contain a JSON object" % db_path)
    missing = [key for key in REQUIRED_DB_KEYS if key not in parsed]
    if missing:
        raise BuildError(
            "%s is missing required top-level key(s): %s"
            % (db_path, ", ".join(missing))
        )
    if SCRIPT_CLOSE_RE in db_text.lower():
        raise BuildError(
            "%s contains a '%s' sequence; embedding it would break out of the "
            "<script id=\"db-data\"> element" % (db_path, SCRIPT_CLOSE_RE)
        )
    return db_text


def _load_template(template_path: Path) -> str:
    template = template_path.read_text(encoding="utf-8").strip()
    occurrences = template.count(PLACEHOLDER)
    if occurrences == 0:
        raise BuildError(
            "template %s is missing the %r marker" % (template_path, PLACEHOLDER)
        )
    if occurrences > 1:
        raise BuildError(
            "template %s contains %r %d times; exactly one is required"
            % (template_path, PLACEHOLDER, occurrences)
        )
    return template


def _write_atomic(output_path: Path, html: str) -> None:
    """Write via a same-directory temp file + os.replace (atomic on POSIX/NTFS)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(
        prefix=output_path.name + ".", suffix=".tmp", dir=str(output_path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(html)  # UTF-8, no BOM
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, output_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def build_html(
    *,
    db_path: Path = DB_PATH,
    template_path: Path = TEMPLATE_PATH,
    output_path: Path = OUTPUT_PATH,
    node_exe: str | None = None,
    run_validate: bool = True,
) -> dict:
    """Assemble `antibiotic_calc.html` from the template + DB payload.

    Returns a report dict (output bytes, output sha256, build stamp).
    """
    if not db_path.is_file():
        raise BuildError("database not found: %s" % db_path)
    if not template_path.is_file():
        raise BuildError("template not found: %s" % template_path)

    validation_report = _run_validate(node_exe) if run_validate else "(skipped)"

    db_json = _load_db(db_path)
    template = _load_template(template_path)

    stamp = build_stamp(db_json, template)
    has_stamp_marker = STAMP_PLACEHOLDER in template
    if has_stamp_marker:
        template = template.replace(STAMP_PLACEHOLDER, stamp)

    html = template.replace(PLACEHOLDER, db_json)
    if PLACEHOLDER in html:
        raise BuildError("the %r marker survived substitution" % PLACEHOLDER)
    _write_atomic(output_path, html)

    return {
        "output": str(output_path),
        "bytes": len(html.encode("utf-8")),
        "sha256": _sha256_text(html),
        "stamp": stamp,
        "stamp_embedded": has_stamp_marker,
        "db_bytes": len(db_json.encode("utf-8")),
        "validation": validation_report,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    node_exe: str | None = None
    run_validate = True
    for i, a in enumerate(argv):
        if a == "--node" and i + 1 < len(argv):
            node_exe = argv[i + 1]
        elif a in ("--skip-validate", "--no-validate"):
            run_validate = False
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print("unknown argument: %s" % a, file=sys.stderr)
            return 2

    try:
        report = build_html(node_exe=node_exe, run_validate=run_validate)
    except (BuildError, FileNotFoundError, OSError) as exc:
        print("BUILD FAILED: %s" % exc, file=sys.stderr)
        return 1

    print("Wrote %s (%d bytes)" % (report["output"], report["bytes"]))
    print("DB embedded: %d chars" % report["db_bytes"])
    if report["stamp_embedded"]:
        print("Build stamp: %s (embedded via %s)" % (report["stamp"], STAMP_PLACEHOLDER))
    else:
        print(
            "Build stamp: %s (computed only: template defines no %s marker)"
            % (report["stamp"], STAMP_PLACEHOLDER)
        )
    print("Output sha256: %s" % report["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
