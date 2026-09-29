"""MinerU fallback extractor. Uses official library."""

from pathlib import Path
from typing import List
import subprocess
import re
import tempfile
import time

from .base import DocumentExtractor, Document, Page


# MinerU emits an explicit page-break marker between pages in its markdown.
_MINERU_PAGE_BREAK = re.compile(r"^\s*(?:<!--\s*page\s*\d+\s*-->|\u2014\s*page\s*\d+\s*\u2014)\s*$",
                                re.IGNORECASE | re.MULTILINE)


def _split_mineru_pages(markdown: str) -> list[str]:
    """Split MinerU markdown into pages on its page-break markers.

    L-37: the whole document used to become ONE ``Page(page_num=0)``, so per-page
    quality assessment saw a single giant page (never "empty") and per-page
    provenance attributed every fact to page 0.  Returns a single page when no
    marker is present, so behaviour degrades to the previous (whole-document)
    result rather than losing the text.
    """
    if not markdown:
        return []
    markers = list(_MINERU_PAGE_BREAK.finditer(markdown))
    if not markers:
        return [markdown]
    pages: list[str] = []
    previous_end = 0
    for marker in markers:
        chunk = markdown[previous_end:marker.start()]
        if chunk.strip():
            pages.append(chunk.strip())
        previous_end = marker.end()
    tail = markdown[previous_end:]
    if tail.strip():
        pages.append(tail.strip())
    return pages or [markdown]


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
        # L-36: the executable was hardcoded to a Windows `Scripts/mineru.exe`
        # path built from sys.prefix, with no environment override, so it was
        # unreachable on every non-Windows machine.  Resolve, in order: an explicit
        # override, a console-script/binary on PATH, then the Windows location.
        override = os.environ.get("ANTIBIO_MINERU_BIN", "").strip()
        if override:
            mineru_exe = override
        else:
            found = shutil.which("mineru")
            if found:
                mineru_exe = found
            else:
                candidate = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin") / (
                    "mineru.exe" if os.name == "nt" else "mineru"
                )
                if not candidate.exists():
                    raise RuntimeError(
                        "MinerU executable not found. Set ANTIBIO_MINERU_BIN, or put "
                        "'mineru' on PATH (install with: pip install mineru)."
                    )
                mineru_exe = str(candidate)
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
            # L-37: MinerU output became a SINGLE Page(page_num=0) holding the whole
            # document, so per-page quality assessment saw one giant page (always
            # "good", never "empty") and per-page provenance/attribution pointed at
            # page 0 for every fact.  Split on MinerU's own page-break marker, which
            # is exactly the page boundary the OCR engine saw.
            page_texts = _split_mineru_pages(md)
            pages = [Page(page_num=i, text=text) for i, text in enumerate(page_texts)]

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
