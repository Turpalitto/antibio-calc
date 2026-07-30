"""Full corpus validation for P4.1.1 extraction pipeline.
Real execution only. Collects metrics for analytics.
"""

import json
import time
import argparse
from pathlib import Path
from clinical_engine.corpus.locator import resolve_corpus_dir
from src.pipeline.extraction.router import ExtractorRouter
from src.pipeline.extraction.metrics import get_metrics, reset_metrics

def find_unique_pdfs(base_path: str) -> list:
    pdfs = {}
    base = Path(base_path)
    for p in base.rglob('*.pdf'):
        if p.is_file() and p.stat().st_size > 1000:
            if p.name not in pdfs:
                pdfs[p.name] = str(p.resolve())
    return list(pdfs.values())

def main(base: str | Path | None = None):
    base = str(Path(base) if base is not None else resolve_corpus_dir())
    print(f'Searching unique PDFs under {base}...')
    pdf_paths = find_unique_pdfs(base)
    print(f'Found {len(pdf_paths)} unique PDFs')

    router = ExtractorRouter()
    reset_metrics()
    stats = []
    errors = []

    for i, pdf_str in enumerate(pdf_paths):
        pdf = Path(pdf_str)
        t0 = time.time()
        try:
            d = router.extract(pdf)
            dt = time.time() - t0
            stat = {
                'name': pdf.name,
                'path': str(pdf),
                'engine': d.source,
                'time_s': round(dt, 2),
                'pages': len(d.pages),
                'text_len': len(d.full_text),
                'md_len': len(getattr(d, 'markdown', '')),
                'tables': len(d.tables),
                'warnings': len(getattr(d, 'warnings', [])),
                'errors': len(getattr(d, 'errors', [])),
                'cache_hit': 'cache' in str(d.source).lower(),
                'confidence': round(d.confidence, 3),
            }
            stats.append(stat)
        except Exception as e:
            dt = time.time() - t0
            err = {
                'name': pdf.name,
                'path': str(pdf),
                'time_s': round(dt, 2),
                'error': str(e)[:200],
            }
            errors.append(err)
            stats.append({
                'name': pdf.name,
                'path': str(pdf),
                'engine': 'error',
                'time_s': round(dt, 2),
                'error': str(e)[:100],
            })

        if (i + 1) % 100 == 0:
            print(f'Processed {i+1}/{len(pdf_paths)}')

    with open('corpus_extraction_stats.json', 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    with open('corpus_extraction_errors.json', 'w', encoding='utf-8') as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)

    print(f'Saved stats for {len(stats)} documents')
    print(f'Errors: {len(errors)}')

    # Quick summary
    success = [s for s in stats if s.get('engine') != 'error']
    print(f'Success: {len(success)} / {len(stats)}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus-dir",
        default=None,
        help="External corpus root; defaults to ANTIBIO_CORPUS_DIR/config.",
    )
    args = parser.parse_args()
    main(args.corpus_dir)
