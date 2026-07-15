"""Classify every Git status entry for reproducibility recovery."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path


CATEGORIES = {
    "A": "source code that must be tracked",
    "B": "required configuration template",
    "C": "migration",
    "D": "documentation",
    "E": "test fixture or test source",
    "F": "generated artifact",
    "G": "local cache/model",
    "H": "sensitive file",
    "I": "production database artifact",
    "J": "obsolete file",
    "TRACKED_MODIFIED": "already tracked, modified",
}


def classify(path: str) -> str:
    value = path.replace("\\", "/").casefold()
    name = Path(value).name
    if "test" in value or "/fixtures/" in value or "/golden_cases/" in value:
        return "E"
    if value.endswith(".md"):
        return "D"
    if name in {".env", ".env.local"} or name.endswith((".pem", ".key")):
        return "H"
    if value.endswith((".sqlite", ".sqlite3", ".db")):
        return "I"
    if any(token in value for token in ("/.venv/", "/__pycache__/", "/models/", "/cache/")):
        return "G"
    if "migration" in value and value.endswith((".py", ".sql", ".md")):
        return "C"
    if name in {".env.example", ".gitleaks.toml", "pyproject.toml", "uv.lock"} or value.startswith("config/"):
        return "B"
    if value.endswith((".py", ".js", ".ps1", ".html", ".template", ".toml", ".yaml", ".yml")):
        return "A"
    if value.endswith((".log", ".csv", ".png", ".json")):
        return "F"
    if any(token in name for token in ("tmp", "backup", "old", "copy")):
        return "J"
    return "F"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="REPOSITORY_UNTRACKED_INVENTORY.json")
    args = parser.parse_args()
    raw = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "-uall"], text=True, encoding="utf-8"
    )
    records = []
    for entry in filter(None, raw.split("\0")):
        status, path = entry[:2], entry[3:]
        category = classify(path) if status == "??" else "TRACKED_MODIFIED"
        records.append({"status": status, "path": path, "category": category,
                        "meaning": CATEGORIES[category]})
    counts = Counter(item["category"] for item in records)
    document = {"schema_version": 1, "total": len(records), "counts": dict(sorted(counts.items())),
                "records": records}
    Path(args.out).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(records), "counts": document["counts"]}))


if __name__ == "__main__":
    main()
