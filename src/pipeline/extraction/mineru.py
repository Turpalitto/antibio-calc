"""MinerU fallback extractor. Uses official library."""

from pathlib import Path
from typing import List
import subprocess
import tempfile
import time

from .base import DocumentExtractor, Document, Page


class MinerUExtractor(DocumentExtractor):
    """MinerU as fallback for scans / low quality."""

    @property
    def name(self) -> str:
        return "mineru"

    def extract(self, pdf_path: Path) -> Document:
        t0 = time.time()
        # Use CLI for stability (avoids heavy import side effects in prod)
        # Output to temp md, parse text.
        # Use temp ASCII name copy to avoid path/encoding issues with original PDF name.
        import sys, os, shutil
        mineru_exe = os.path.join(sys.prefix, 'Scripts', 'mineru.exe')
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            # Copy to simple name to avoid CLI temp path issues with special chars in name
            simple_pdf = Path(tmp) / "input.pdf"
            shutil.copy(str(pdf_path), str(simple_pdf))
            cmd = [
                mineru_exe,
                "-p", str(simple_pdf),
                "-o", str(out_dir),
                "--backend", "pipeline",
                "--method", "ocr",
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
            except Exception as e:
                raise RuntimeError(f"MinerU failed on {pdf_path}: {e}")

            # Find the .md
            mds = list(out_dir.rglob("*.md"))
            if not mds:
                raise RuntimeError(f"MinerU produced no output for {pdf_path}")

            md = mds[0].read_text(encoding="utf-8", errors="ignore")
            pages = [Page(page_num=0, text=md)]  # MinerU gives unified md; can split if needed

            elapsed = (time.time() - t0) * 1000
            return Document(
                source="mineru",
                pdf_path=pdf_path,
                pages=pages,
                full_text=md,
                markdown=md,
                confidence=0.85,  # high for OCR
                metadata={"backend": "pipeline"},
                elapsed_time_ms=elapsed,
            )
