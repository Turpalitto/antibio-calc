"""Cross-platform Python port of the Windows `build_html.ps1` script.

The original PowerShell build is Windows-only; this module reproduces it so the
single-page HTML calculator can be built on any OS (e.g. macOS).

Procedure (mirrors build_html.ps1):
  1. run `node db/validate_db.js` (throw if it exits non-zero — the DB is
     invalid and must never be embedded);
  2. read `db/antibio_db.json` (the source of truth for the calculator);
  3. read `antibiotic_calc.html.template`;
  4. assert the template contains the single `__DB_PLACEHOLDER__` marker;
  5. replace that marker with the DB JSON payload (the data is embedded
     literally);
  6. write `antibiotic_calc.html` as UTF-8 without BOM.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "antibio_db.json"
TEMPLATE_PATH = PROJECT_ROOT / "antibiotic_calc.html.template"
OUTPUT_PATH = PROJECT_ROOT / "antibiotic_calc.html"
PLACEHOLDER = "__DB_PLACEHOLDER__"


def _run_validate(node_exe: str | None = None) -> None:
    """Run `node db/validate_db.js` and raise if it fails."""
    exe = node_exe or "node"
    script = PROJECT_ROOT / "db" / "validate_db.js"
    if not script.exists():
        return
    proc = subprocess.run(
        [exe, str(script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "db/validate_db.js failed (exit %s):\n%s"
            % (proc.returncode, (proc.stdout or "") + (proc.stderr or ""))
        )


def build_html(
    *,
    db_path: Path = DB_PATH,
    template_path: Path = TEMPLATE_PATH,
    output_path: Path = OUTPUT_PATH,
    node_exe: str | None = None,
    run_validate: bool = True,
) -> int:
    """Assemble `antibiotic_calc.html` from the template + DB payload."""
    if run_validate:
        _run_validate(node_exe)

    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")

    db_json = db_path.read_text(encoding="utf-8-sig").strip()
    template = template_path.read_text(encoding="utf-8").strip()

    if PLACEHOLDER not in template:
        raise RuntimeError(f"template is missing the {PLACEHOLDER!r} marker")

    html = template.replace(PLACEHOLDER, db_json)
    output_path.write_text(html, encoding="utf-8")  # UTF-8, no BOM
    return len(html)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    node_exe: str | None = None
    for i, a in enumerate(argv):
        if a == "--node" and i + 1 < len(argv):
            node_exe = argv[i + 1]
    length = build_html(node_exe=node_exe)
    print(f"Wrote {OUTPUT_PATH} ({length} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
