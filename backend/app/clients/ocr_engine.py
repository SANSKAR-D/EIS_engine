# backend/app/clients/ocr_engine.py
import inspect
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import fitz  # PyMuPDF
from app.config import settings
from app.schemas.ingest import AttachmentPageArtifact

_rapid_ocr = None


def get_rapid_ocr():
    """Lazy loader for RapidOCR instance."""
    global _rapid_ocr
    if _rapid_ocr is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapid_ocr = RapidOCR()
        except ImportError:
            _rapid_ocr = None
    return _rapid_ocr


def _table_to_markdown(table: List[List[Optional[str]]]) -> str:
    """Converts a 2D table grid from pdfplumber into clean GitHub Flavored Markdown."""
    rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in table if any(r)]
    if not rows:
        return ""
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([header, sep, *body])


def _run_rapidocr_bytes(img_bytes: bytes, ocr_instance: Any = None) -> Tuple[str, float]:
    """Runs RapidOCR on image bytes and returns (extracted_text, mean_confidence)."""
    ocr = ocr_instance or get_rapid_ocr()
    if ocr is None:
        return "", 0.0

    result, _ = ocr(img_bytes)
    if not result:
        return "", 0.0
    lines = [item[1] for item in result]
    confs = [float(item[2]) for item in result]
    mean_conf = (sum(confs) / len(confs)) if confs else 0.0
    return "\n".join(lines), mean_conf


async def parse_pdf_attachment(
    email_id: str,
    file_path: Union[Path, str],
    allow_vision: bool = True,
    vision_fn: Optional[Callable] = None,
    ocr_instance: Any = None,
) -> List[AttachmentPageArtifact]:
    """
    Parses a PDF attachment:
    - Digital pages (text > 50 chars): uses pdfplumber for table preservation.
    - Scanned pages: renders 200 DPI pixmap and runs local RapidOCR on CPU.
    - Low-confidence scanned pages (< 0.75): escalates to vision_fn if allow_vision=True.
    """
    path = Path(file_path)
    artifacts: List[AttachmentPageArtifact] = []

    try:
        import pdfplumber
    except ImportError:
        pdfplumber = None

    doc = fitz.open(path)

    plumber_pdf = None
    if pdfplumber is not None:
        try:
            plumber_pdf = pdfplumber.open(path)
        except Exception:
            plumber_pdf = None

    try:
        for idx, fitz_page in enumerate(doc):
            page_num = idx + 1
            raw_text = fitz_page.get_text("text").strip()

            if len(raw_text) > 50:
                md_tables: List[str] = []
                if plumber_pdf is not None and idx < len(plumber_pdf.pages):
                    try:
                        p_page = plumber_pdf.pages[idx]
                        tables = p_page.extract_tables() or []
                        md_tables = [_table_to_markdown(t) for t in tables if t]
                    except Exception:
                        md_tables = []

                combined = raw_text
                if md_tables:
                    combined += "\n\n" + "\n\n".join(md_tables)

                artifacts.append(AttachmentPageArtifact(
                    email_id=email_id,
                    filename=path.name,
                    page_number=page_num,
                    extraction_method="PDFPLUMBER",
                    mean_confidence=1.0,
                    extracted_text=combined.strip(),
                    has_tables=bool(md_tables),
                ))
            else:
                pix = fitz_page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                ocr_text, conf = _run_rapidocr_bytes(img_bytes, ocr_instance=ocr_instance)
                method = "RAPIDOCR"
                final_text = ocr_text

                # Calibrated Vision fallback hook (< 0.75 cutoff)
                if conf < settings.ocr_vision_fallback_cutoff and allow_vision and vision_fn:
                    if inspect.iscoroutinefunction(vision_fn):
                        v_res = await vision_fn(img_bytes)
                    else:
                        v_res = vision_fn(img_bytes)
                    if v_res:
                        final_text = v_res
                        method = "GEMINI_VISION"
                        conf = 1.0

                artifacts.append(AttachmentPageArtifact(
                    email_id=email_id,
                    filename=path.name,
                    page_number=page_num,
                    extraction_method=method,
                    mean_confidence=round(conf, 4),
                    extracted_text=final_text.strip(),
                    has_tables=False,
                ))
    finally:
        if plumber_pdf is not None:
            plumber_pdf.close()
        doc.close()

    return artifacts


async def extract_email_attachments(
    email_id: str,
    active_attachments: List[Dict[str, Any]],
    allow_vision: bool = True,
    vision_fn: Optional[Callable] = None,
    ocr_instance: Any = None,
) -> List[AttachmentPageArtifact]:
    """Extracts all active attachments for an email across PDF, Image, and Text formats."""
    all_artifacts: List[AttachmentPageArtifact] = []

    for att in active_attachments:
        p_str = att.get("file_path") or att.get("filename") or ""
        p = Path(p_str)
        if not p.exists():
            continue

        ext = p.suffix.lower()
        if ext == ".pdf":
            pages = await parse_pdf_attachment(
                email_id=email_id,
                file_path=p,
                allow_vision=allow_vision,
                vision_fn=vision_fn,
                ocr_instance=ocr_instance,
            )
            all_artifacts.extend(pages)
        elif ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            img_bytes = p.read_bytes()
            ocr_text, conf = _run_rapidocr_bytes(img_bytes, ocr_instance=ocr_instance)
            method = "RAPIDOCR"
            final_text = ocr_text

            if conf < settings.ocr_vision_fallback_cutoff and allow_vision and vision_fn:
                if inspect.iscoroutinefunction(vision_fn):
                    v_res = await vision_fn(img_bytes)
                else:
                    v_res = vision_fn(img_bytes)
                if v_res:
                    final_text = v_res
                    method = "GEMINI_VISION"
                    conf = 1.0

            all_artifacts.append(AttachmentPageArtifact(
                email_id=email_id,
                filename=p.name,
                page_number=1,
                extraction_method=method,
                mean_confidence=round(conf, 4),
                extracted_text=final_text.strip(),
                has_tables=False,
            ))
        elif ext in {".txt", ".csv"}:
            txt = p.read_text(encoding="utf-8", errors="replace").strip()
            all_artifacts.append(AttachmentPageArtifact(
                email_id=email_id,
                filename=p.name,
                page_number=1,
                extraction_method="PDFPLUMBER",
                mean_confidence=1.0,
                extracted_text=txt,
                has_tables=(ext == ".csv"),
            ))

    return all_artifacts
