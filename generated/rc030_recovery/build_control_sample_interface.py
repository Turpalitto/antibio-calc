"""RC-030 owner control-sample interface build script.

Turns owner_control_sample_template.html + owner_control_sample_data.json
into the owner-facing RC030_OWNER_CONTROL_SAMPLE_INTERFACE.html.

Usage: python generated/rc030_recovery/build_control_sample_interface.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "owner_control_sample_template.html"
DATA = HERE / "owner_control_sample_data.json"
OUTPUT = HERE / "RC030_OWNER_CONTROL_SAMPLE_INTERFACE.html"
PLACEHOLDER = "__RECORDS_JSON__"


def build() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"template is missing the {PLACEHOLDER} placeholder — refusing to build a broken file")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    records = data["records"]
    if len(records) != 30:
        raise SystemExit(f"expected exactly 30 control-sample records, found {len(records)} — refusing to build")
    records_json = json.dumps(records, ensure_ascii=False)
    final = template.replace(PLACEHOLDER, records_json)
    OUTPUT.write_text(final, encoding="utf-8")
    print(f"built {OUTPUT} ({len(final)} bytes, {len(records)} records)")


if __name__ == "__main__":
    build()
