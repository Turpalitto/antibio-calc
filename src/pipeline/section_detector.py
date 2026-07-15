import logging
import re
from pathlib import Path

from config import ANTIBIOTIC_NAMES, DOSING_PATTERNS, SECTION_PATTERNS

logger = logging.getLogger(__name__)

_SECTION_RE = [re.compile(p, re.IGNORECASE) for p in SECTION_PATTERNS]
_DOSING_RE = [re.compile(p, re.IGNORECASE) for p in DOSING_PATTERNS]
_ABX_NAMES_LOWER = [n.lower() for n in ANTIBIOTIC_NAMES]


def extract_text_per_page(pdf_path: Path) -> list[str]:
    if not pdf_path.exists():
        logger.warning(f"  PDF not found: {pdf_path}")
        return []

    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed")
        return []

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.warning(f"  Cannot open PDF {pdf_path}: {exc}")
        return []

    pages: list[str] = []
    for page_num in range(len(doc)):
        try:
            page = doc[page_num]
            text = page.get_text("text") or ""
            pages.append(text)
        except Exception as exc:
            logger.debug(f"  Page {page_num} error: {exc}")
            pages.append("")

    doc.close()
    return pages


def _find_sections(text: str, page_num: int) -> list[dict]:
    found = []
    for pattern in _SECTION_RE:
        for match in pattern.finditer(text):
            section_name = match.group(1) if match.groups() else match.group(0)
            section_name = section_name.strip()
            found.append({"section": section_name, "page": page_num})
    return found


def _has_dosing(text: str) -> bool:
    for pattern in _DOSING_RE:
        if pattern.search(text):
            return True
    return False


def _count_abx_names(text: str) -> int:
    text_lower = text.lower()
    return sum(1 for name in _ABX_NAMES_LOWER if name in text_lower)


def detect_sections(pdf_path: Path, clinrec_id: int = 0) -> dict:
    pages = extract_text_per_page(pdf_path)
    total_pages = len(pages)

    if total_pages == 0:
        return {
            "clinrec_id": clinrec_id,
            "total_pages": 0,
            "relevant_pages": [],
            "relevant_text": "",
            "sections_found": [],
            "dosing_pages": [],
        }

    sections_found: list[dict] = []
    section_pages: set[int] = set()
    dosing_pages: set[int] = set()

    for page_num, text in enumerate(pages):
        sections = _find_sections(text, page_num)
        if sections:
            sections_found.extend(sections)
            section_pages.add(page_num)
        if _has_dosing(text):
            dosing_pages.add(page_num)

    high_priority = dosing_pages & section_pages
    medium_priority = dosing_pages - section_pages
    low_priority = section_pages - dosing_pages

    relevant_set = high_priority | medium_priority
    for p in sorted(low_priority):
        if len(relevant_set) >= 20:
            break
        relevant_set.add(p)

    for p in list(relevant_set):
        if p + 1 < total_pages and p + 1 not in relevant_set:
            if _has_dosing(pages[p + 1]):
                relevant_set.add(p + 1)

    dosing_relevant = sorted(p for p in relevant_set if p in dosing_pages)
    other_relevant = sorted(p for p in relevant_set if p not in dosing_pages)
    relevant_pages = sorted(
        relevant_set,
        key=lambda p: (-_count_abx_names(pages[p]), p not in dosing_pages, p),
    )

    parts = []
    for p in relevant_pages:
        marker = f"--- Страница {p + 1} ---"
        parts.append(f"{marker}\n{pages[p]}")
    relevant_text = "\n\n".join(parts) if relevant_pages else ""

    return {
        "clinrec_id": clinrec_id,
        "total_pages": total_pages,
        "relevant_pages": relevant_pages,
        "relevant_text": relevant_text,
        "sections_found": sections_found,
        "dosing_pages": sorted(dosing_pages),
    }
