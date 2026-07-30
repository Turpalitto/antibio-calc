"""Build P5.6 review store from immutable production inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from clinical_engine.corpus.locator import CorpusLocator
from clinical_engine.review_workbench.queue_builder import build_initial_queue


def main() -> None:
    corpus = CorpusLocator()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--normalized-db",
        default=str(corpus.normalized_regimens_sqlite),
        help="Defaults to ANTIBIO_CORPUS_DIR/normalized_regimens.sqlite.",
    )
    parser.add_argument("--kb-db", default="kb_p44.db")
    parser.add_argument("--corpus-manifest", default="CORPUS_MANIFEST.json")
    parser.add_argument("--issues", default="clinical_data_issues.json")
    parser.add_argument("--golden-directory", default="clinical_engine/golden_cases")
    parser.add_argument("--out", default="review_workbench.sqlite")
    parser.add_argument("--report", default="p56_queue_report.json")
    args = parser.parse_args()
    if Path(args.out).exists():
        raise FileExistsError(f"Refusing to alter existing review store: {args.out}")
    report = build_initial_queue(
        store_path=args.out, normalized_db=args.normalized_db, kb_db=args.kb_db,
        corpus_manifest=args.corpus_manifest, issues_json=args.issues,
        golden_directory=args.golden_directory,
    )
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["queue_metrics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
