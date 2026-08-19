"""Layout module for P4.5 — Production Layout Intelligence Platform.

DocLayout-YOLO (general regions: title/text/table/figure/list/...)
+ Microsoft Table Transformer (detection + structure)
+ RapidTable (robust table fallback + OCR)

Produces:
- layout_blocks (headings, paragraphs, tables, figures, etc. with bboxes)
- structured_tables (TableObject with real cells, row/col, provenance)

All output is engine-agnostic. Full cell-level lineage for traceability.
CPU fallback guaranteed. Backward compatible with dict tables.
"""

import sys
import os
import io
import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import time

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def _rapidtable_html(result) -> str:
    """RC-016: adapt to RapidTable API drift. New rapid-table (>=3) returns a RapidTableOutput with
    `.pred_htmls` (list); older versions returned a (html, elapse) tuple. Return first HTML or ""."""
    htmls = getattr(result, "pred_htmls", None)
    if htmls:
        return htmls[0] if isinstance(htmls, (list, tuple)) and htmls else (htmls or "")
    if isinstance(result, (list, tuple)) and result:
        return result[0]
    return ""

# Optional external site-packages directory for heavyweight extraction deps
# (DocLayout-YOLO / Table Transformer / RapidTable) when they live outside the
# active environment. Opt-in only via ANTIBIO_EXTERNAL_SITE_PACKAGES — never a
# hard-coded, machine-specific path. See .env.example.
_external_site_packages = os.environ.get("ANTIBIO_EXTERNAL_SITE_PACKAGES", "").strip()
if _external_site_packages:
    if not os.path.isdir(_external_site_packages):
        raise RuntimeError(
            "ANTIBIO_EXTERNAL_SITE_PACKAGES is set but does not point to an "
            f"existing directory: {_external_site_packages!r}"
        )
    if _external_site_packages not in sys.path:
        sys.path.insert(0, _external_site_packages)

# Import our structured models (additive)
from .base import (
    Document, Page, BoundingBox, TableCell, TableObject,
)


class LayoutProcessor:
    """Production Layout + Table Engine.

    Detects layout elements and extracts structured tables with cells.
    """

    def __init__(self, device: str = "cpu"):
        self.device = device
        self.doclayout_model = None
        self.table_detector = None
        self.table_detector_processor = None
        self.table_structure = None
        self.table_structure_processor = None
        self.rapid_table = None
        self._load_models()

    def _load_models(self):
        # 1. DocLayout-YOLO for general page layout (headings, tables regions, etc.)
        try:
            from doclayout_yolo import YOLO
            from huggingface_hub import hf_hub_download
            model_path = hf_hub_download(
                repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
                filename="doclayout_yolo_docstructbench_imgsz1024.pt"
            )
            self.doclayout_model = YOLO(model_path)
            print("[Layout] DocLayout-YOLO loaded (0.0.4)")
        except Exception as e:
            print(f"[Layout] DocLayout-YOLO load warning (will use text fallback): {e}")
            self.doclayout_model = None

        # 2. Microsoft Table Transformer (detection + structure)
        try:
            from transformers import AutoImageProcessor, AutoModelForObjectDetection
            self.table_detector_processor = AutoImageProcessor.from_pretrained(
                "microsoft/table-transformer-detection"
            )
            self.table_detector = AutoModelForObjectDetection.from_pretrained(
                "microsoft/table-transformer-detection"
            )
            self.table_structure_processor = AutoImageProcessor.from_pretrained(
                "microsoft/table-transformer-structure-recognition"
            )
            self.table_structure = AutoModelForObjectDetection.from_pretrained(
                "microsoft/table-transformer-structure-recognition"
            )
            print("[Layout] Table Transformer (detection + structure) loaded")
        except Exception as e:
            print(f"[Layout] Table Transformer load warning: {e}")
            self.table_detector = None
            self.table_structure = None

        # 3. RapidTable (strong fallback for end-to-end table HTML/structured)
        try:
            from rapid_table import RapidTable
            self.rapid_table = RapidTable()
            print("[Layout] RapidTable loaded (3.0.2)")
        except Exception as e:
            print(f"[Layout] RapidTable load warning: {e}")
            self.rapid_table = None

    def _scale_bbox(self, bbox: List[float], img_w: int, img_h: int,
                    page_rect: fitz.Rect, page_num: int) -> BoundingBox:
        """Scale image bbox (pixels) back to PDF points."""
        x0, y0, x1, y1 = bbox
        scale_x = page_rect.width / img_w
        scale_y = page_rect.height / img_h
        return BoundingBox(
            x0=x0 * scale_x,
            y0=y0 * scale_y,
            x1=x1 * scale_x,
            y1=y1 * scale_y,
            page=page_num
        )

    def _extract_text_in_bbox(self, page: fitz.Page, bbox: BoundingBox) -> str:
        """Use fitz to pull accurate text inside PDF bbox (preferred over OCR when possible)."""
        try:
            rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
            text = page.get_text("text", clip=rect) or ""
            return text.strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_native_cell_text(page: fitz.Page, rect: fitz.Rect) -> str:
        """Extract one digital-PDF table cell while preserving footnote semantics.

        ``Table.extract()`` concatenates superscript footnote markers with the
        preceding number (for example ``50-60¹`` becomes ``50-601``).  That is
        unsafe for clinical doses.  PyMuPDF exposes the superscript bit on the
        original span, so keep the marker explicit and non-numeric instead.
        """
        blocks = page.get_text("dict", clip=rect).get("blocks", [])
        lines: List[str] = []
        for block in blocks:
            for line in block.get("lines", []):
                parts: List[str] = []
                for span in line.get("spans", []):
                    value = str(span.get("text") or "")
                    if not value:
                        continue
                    flags = int(span.get("flags") or 0)
                    if flags & 1 and value.strip().isdigit():
                        parts.append(f"[fn:{value.strip()}]")
                    else:
                        parts.append(value)
                text = "".join(parts).strip()
                if text:
                    lines.append(text)
        return "\n".join(lines).strip()

    def _extract_tables_pymupdf_native(
        self, page: fitz.Page, page_num: int, source_pdf: str
    ) -> List[TableObject]:
        """Primary fallback for born-digital PDFs using native ruled tables.

        This path has no heavyweight ML dependency and retains exact row/column,
        cell bbox, page, source PDF and explicit footnote markers.
        """
        tables: List[TableObject] = []
        try:
            finder = page.find_tables()
        except Exception as exc:
            logger.warning("PyMuPDF native table detection failed on page %s: %s", page_num, exc)
            return tables

        for native in finder.tables:
            cells: List[TableCell] = []
            for row_index, row in enumerate(native.rows):
                for col_index, raw_bbox in enumerate(row.cells):
                    if raw_bbox is None:
                        continue
                    rect = fitz.Rect(raw_bbox)
                    bbox = BoundingBox(*raw_bbox, page=page_num)
                    cells.append(TableCell(
                        row=row_index,
                        col=col_index,
                        text=self._extract_native_cell_text(page, rect),
                        bbox=bbox,
                        confidence=0.97,
                        engine="pymupdf-native-table",
                        source_pdf=source_pdf,
                        page_num=page_num,
                    ))
            if not cells:
                continue
            table_bbox = BoundingBox(*native.bbox, page=page_num)
            tables.append(TableObject(
                page_num=page_num,
                bbox=table_bbox,
                rows=native.row_count,
                cols=native.col_count,
                cells=cells,
                header_rows=0,
                confidence=0.97,
                engine="pymupdf-native-table",
                source_pdf=source_pdf,
            ))
        return tables

    def _build_cells_from_words(self, page: fitz.Page, table_bbox: BoundingBox, approx_rows: int, approx_cols: int) -> List[TableCell]:
        """Production-grade: extract words with bboxes inside table region and cluster into grid."""
        cells: List[TableCell] = []
        try:
            rect = fitz.Rect(table_bbox.x0, table_bbox.y0, table_bbox.x1, table_bbox.y1)
            words = page.get_text("words", clip=rect)  # list of (x0,y0,x1,y1, word, block, line, word_no)
            if not words:
                return cells

            # Simple grid clustering by quantizing y then x
            # Group by approximate row using y centers
            rows_map = defaultdict(list)
            for w in words:
                x0, y0, x1, y1, word = w[0], w[1], w[2], w[3], w[4]
                cy = (y0 + y1) / 2
                row_key = int((cy - table_bbox.y0) / max(1, (table_bbox.y1 - table_bbox.y0) / max(1, approx_rows)))
                rows_map[row_key].append((x0, y0, x1, y1, word))

            for r, row_words in sorted(rows_map.items()):
                # sort by x
                row_words.sort(key=lambda ww: ww[0])
                # distribute into cols
                col_width = max(1, (table_bbox.x1 - table_bbox.x0) / max(1, approx_cols))
                for ww in row_words:
                    cx = (ww[0] + ww[2]) / 2
                    c = int((cx - table_bbox.x0) / col_width)
                    c = max(0, min(approx_cols-1, c))
                    cell_bbox = BoundingBox(ww[0], ww[1], ww[2], ww[3], table_bbox.page)
                    cells.append(TableCell(
                        row=r, col=c,
                        text=ww[4],
                        bbox=cell_bbox,
                        confidence=0.9,
                        engine="fitz+layout",
                        page_num=table_bbox.page
                    ))
        except Exception:
            pass
        return cells

    def _run_doclayout(self, image: Image.Image, page_num: int, page_rect: fitz.Rect) -> List[Dict]:
        blocks = []
        if not self.doclayout_model:
            return blocks
        try:
            with tempfile.TemporaryDirectory() as tmp:
                img_path = os.path.join(tmp, "page.png")
                image.save(img_path)
                res = self.doclayout_model.predict(img_path, imgsz=1024, conf=0.25, device=self.device)
                for box in res[0].boxes:
                    cls_id = int(box.cls)
                    label = res[0].names.get(cls_id, str(cls_id))
                    xyxy = box.xyxy[0].tolist()
                    conf = float(box.conf)
                    blocks.append({
                        "type": label,
                        "bbox": xyxy,
                        "confidence": conf,
                        "page": page_num,
                    })
        except Exception as e:
            blocks.append({"type": "error", "msg": str(e)[:120]})
        return blocks

    def _extract_table_with_transformers(self, image: Image.Image, page: fitz.Page,
                                         page_num: int, page_rect: fitz.Rect) -> List[TableObject]:
        """Primary table path using Table Transformer detection + structure + fitz text."""
        tables: List[TableObject] = []
        if not (self.table_detector and self.table_structure):
            return tables

        try:
            import torch
            from transformers import TableTransformerForObjectDetection

            # Detection
            inputs = self.table_detector_processor(images=image, return_tensors="pt")
            outputs = self.table_detector(**inputs)
            target_sizes = torch.tensor([image.size[::-1]])
            results = self.table_detector_processor.post_process_object_detection(
                outputs, threshold=0.7, target_sizes=target_sizes
            )[0]

            for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
                if label.item() != 0:  # 0 is usually "table" in the model
                    continue
                x0, y0, x1, y1 = [round(v.item()) for v in box]
                table_bbox_img = [x0, y0, x1, y1]
                conf = float(score.item())
                # PR-001 fix: scaled table bbox must be computed BEFORE it is used by
                # _build_cells_from_words below. Previously `tbbox` was referenced (line ~266)
                # before its assignment (line ~270), raising NameError on every detected table,
                # which the bare `except` swallowed — silently dropping ALL structured tables.
                tbbox = self._scale_bbox(table_bbox_img, image.width, image.height, page_rect, page_num)

                # Crop for structure recognition
                table_img = image.crop((x0, y0, x1, y1))

                # Structure recognition
                s_inputs = self.table_structure_processor(images=table_img, return_tensors="pt")
                s_outputs = self.table_structure(**s_inputs)
                s_target_sizes = torch.tensor([table_img.size[::-1]])
                s_results = self.table_structure_processor.post_process_object_detection(
                    s_outputs, threshold=0.6, target_sizes=s_target_sizes
                )[0]

                # Build cells from structure (simplified but functional: group by row/col spans)
                cells: List[TableCell] = []
                # The structure model outputs many small boxes for rows/cols/headers/cells.
                # For production we collect "cell" like objects and assign approximate row/col.
                # A robust implementation would use the full table structure pipeline.
                # Here we use a practical grouping.

                # Fallback: use RapidTable on the crop for real HTML + parse simple cells
                cell_texts = []
                if self.rapid_table:
                    try:
                        html = _rapidtable_html(self.rapid_table(table_img))
                        # Very lightweight parse of <td>/<th> (production would use proper parser)
                        import re
                        tds = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', html, re.I | re.DOTALL)
                        cell_texts = [re.sub(r'<[^>]+>', '', t).strip() for t in tds]
                    except Exception:
                        pass

                # Create a basic grid (we will improve with real spans in follow-up if needed)
                # For now synthesize a single-row or use detected cell count
                n_cells = max(len(cell_texts), 1)
                cols_est = max(1, min(8, n_cells))  # heuristic
                rows_est = max(1, (n_cells + cols_est - 1) // cols_est)

                for idx, txt in enumerate(cell_texts[:rows_est * cols_est]):
                    r = idx // cols_est
                    c = idx % cols_est
                    cell_bbox = BoundingBox(x0 + (c * (x1-x0)//cols_est), y0 + (r * (y1-y0)//rows_est),
                                            x0 + ((c+1) * (x1-x0)//cols_est), y0 + ((r+1) * (y1-y0)//rows_est),
                                            page=page_num)
                    cells.append(TableCell(
                        row=r, col=c, text=txt or self._extract_text_in_bbox(page, cell_bbox),
                        bbox=cell_bbox, confidence=conf * 0.9,
                        engine="table-transformer+rapidtable", page_num=page_num
                    ))

                if not cells:
                    # At least one cell from full table bbox + text
                    full_text = self._extract_text_in_bbox(page, self._scale_bbox(table_bbox_img, image.width, image.height, page_rect, page_num))
                    cells = [TableCell(row=0, col=0, text=full_text, bbox=self._scale_bbox(table_bbox_img, image.width, image.height, page_rect, page_num),
                                       confidence=conf, engine="table-transformer", page_num=page_num)]

                # Improve cells using actual PDF words (much better for digital PDFs)
                word_cells = self._build_cells_from_words(page, tbbox, rows_est, cols_est)
                if word_cells:
                    cells = word_cells

                # tbbox already computed above (PR-001 fix)
                tables.append(TableObject(
                    page_num=page_num,
                    bbox=tbbox,
                    rows=rows_est,
                    cols=cols_est,
                    cells=cells,
                    header_rows=1 if any("header" in (c.text or "").lower() for c in cells) else 0,
                    confidence=conf,
                    engine="table-transformer+rapidtable",
                    source_pdf=str(page.parent) if hasattr(page, 'parent') else ""
                ))
        except Exception as e:
            # Observability (PR-001): a silent `pass` here hid a NameError that dropped ALL
            # structured tables. Log so any future table-extraction breakage is visible.
            logger.warning("Table Transformer path failed on page %s: %s", page_num, e)
        return tables

    def _extract_tables_rapid_only(self, image: Image.Image, page: fitz.Page, page_num: int, page_rect: fitz.Rect) -> List[TableObject]:
        """RapidTable fallback path (end-to-end)."""
        tables = []
        if not self.rapid_table:
            return tables
        try:
            html = _rapidtable_html(self.rapid_table(image))  # full page; in real use we crop first
            # Create a coarse table object
            tbbox = BoundingBox(0, 0, page_rect.width, page_rect.height, page=page_num)
            # Simple cell extraction from html
            import re
            cells_raw = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', html, re.I | re.DOTALL)
            cells = []
            for i, txt in enumerate(cells_raw[:20]):  # limit
                cells.append(TableCell(row=i//4, col=i % 4, text=re.sub('<[^>]+>', '', txt).strip(),
                                       confidence=0.65, engine="rapidtable", page_num=page_num))
            if cells:
                tables.append(TableObject(
                    page_num=page_num, bbox=tbbox, rows=5, cols=4, cells=cells,
                    confidence=0.65, engine="rapidtable", source_pdf=""
                ))
        except Exception as e:
            logger.warning("RapidTable fallback failed on page %s: %s", page_num, e)
        return tables

    def process_pdf(self, pdf_path: Path) -> Tuple[List[Dict[str, Any]], List[TableObject]]:
        """Returns (layout_blocks per page, structured_tables list).
        
        Production optimization: Skip expensive image-based layout on pages that have no dosing/antibiotic signals (using fast text check).
        This makes full-corpus reprocessing feasible.
        """
        doc = fitz.open(str(pdf_path))
        all_blocks: List[Dict] = []
        all_structured: List[TableObject] = []

        dosing_keywords = ['мг', 'г ', 'мг/кг', 'раз в', 'сутки', 'дней', 'таблиц', 'антибактериальн']

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text") or ""
            page_lower = page_text.lower()

            # Fast skip for pages without relevant content (makes full corpus feasible)
            has_signal = any(kw in page_lower for kw in dosing_keywords)
            if not has_signal and page_num > 2:  # process first pages + any with signals
                all_blocks.append({"page_num": page_num, "blocks": [], "tables": []})
                continue

            # Use lower DPI for layout (structure detection works well at 72-100 DPI, much faster for full corpus)
            layout_dpi = 100
            pix = page.get_pixmap(dpi=layout_dpi)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            page_rect = page.rect

            # Layout blocks (DocLayout-YOLO)
            blocks = self._run_doclayout(image, page_num, page_rect)

            # Tables — native digital-PDF path first; image/ML fallbacks for scans.
            structured = self._extract_tables_pymupdf_native(page, page_num, str(pdf_path))
            if not structured:
                structured = self._extract_table_with_transformers(image, page, page_num, page_rect)
            if not structured:
                structured = self._extract_tables_rapid_only(image, page, page_num, page_rect)

            legacy_tables = [t.to_dict() for t in structured]

            all_blocks.append({
                "page_num": page_num,
                "blocks": blocks,
                "tables": legacy_tables,
            })
            all_structured.extend(structured)

        doc.close()
        return all_blocks, all_structured


def add_layout_to_document(doc: 'Document', pdf_path: Path) -> None:
    """Production integration point. Populates both legacy and structured forms."""
    processor = LayoutProcessor()
    page_layouts, structured_tables = processor.process_pdf(pdf_path)

    # Distribute per page
    per_page_struct: Dict[int, List[TableObject]] = {}
    for t in structured_tables:
        per_page_struct.setdefault(t.page_num, []).append(t)

    for i, layout in enumerate(page_layouts):
        if i < len(doc.pages):
            p = doc.pages[i]
            p.layout_blocks = layout.get("blocks", [])
            legacy = layout.get("tables", [])
            p.tables.extend(legacy)  # additive to any existing
            p.structured_tables = per_page_struct.get(i, [])

    # Aggregate at document level (convenience)
    doc.tables.extend([t for pl in page_layouts for t in pl.get("tables", [])])
    doc.structured_tables.extend(structured_tables)

    doc.metadata["layout_engine"] = "pymupdf-native-table + doclayout-yolo + table-transformer + rapidtable"
    doc.metadata["layout_processed"] = True
    doc.metadata["layout_table_count"] = len(structured_tables)
