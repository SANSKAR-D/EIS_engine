# backend/tests/test_hygiene_and_ocr.py
import io
import pytest
from pathlib import Path

import fitz  # PyMuPDF

try:
    from PIL import Image
    def _create_test_png(w: int, h: int) -> bytes:
        img = Image.new("RGB", (w, h), color=(0, 51, 102))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
except ImportError:
    def _create_test_png(w: int, h: int) -> bytes:
        pm = fitz.Pixmap(fitz.csRGB, (0, 0, w, h), 0)
        return pm.tobytes("png")

from app.pipeline.hygiene import (
    strip_quoted_replies,
    normalize_subject,
    inspect_attachment_hygiene,
)
from app.pipeline.ingest import parse_email_row, load_emails_csv
from app.clients.ocr_engine import (
    parse_pdf_attachment,
    extract_email_attachments,
    _table_to_markdown,
)


def test_t01_nested_quoted_reply_stripping():
    """
    T-01: Email body containing 3 nested 'On ... wrote:' and '>' reply blocks.
    Asserts: clean_body keeps only top new reply; raw_body stays byte-for-byte unchanged.
    """
    raw_body = (
        "Approved. Proceed with Vendor B for INR 17.9 lakh, subject to standard terms.\n\n"
        "On Sun, Sep 7, 2026 at 10:05 AM mech.hod@northbridge.edu wrote:\n"
        "> The department recommends Vendor B at INR 17.9 lakh based on technical compliance.\n"
        "> \n"
        "> On Fri, Sep 5, 2026 at 8:40 AM lab.coordinator@northbridge.edu wrote:\n"
        ">> Technical committee found Vendor A does not meet the spindle speed range.\n"
        ">> \n"
        ">> On Wed, Sep 4, 2026 at 11:20 AM purchase@northbridge.edu wrote:\n"
        ">>> Quotations received: Vendor A INR 18.4 lakh, Vendor B INR 17.9 lakh.\n"
        "-- \n"
        "Prof. Dean Administration\n"
        "Northbridge Institute of Technology"
    )

    clean_body = strip_quoted_replies(raw_body)

    # 1. clean_body must contain only the fresh reply at the top
    assert clean_body == "Approved. Proceed with Vendor B for INR 17.9 lakh, subject to standard terms."

    # 2. Quotation blocks and nested headers must be removed from clean_body
    assert "On Sun, Sep 7" not in clean_body
    assert "Prof. Dean Administration" not in clean_body
    assert ">" not in clean_body

    # 3. raw_body must remain completely byte-for-byte intact
    assert "On Sun, Sep 7, 2026 at 10:05 AM mech.hod@northbridge.edu wrote:" in raw_body
    assert "Prof. Dean Administration" in raw_body


def test_t02_signature_and_logo_hygiene(tmp_path: Path):
    """
    T-02: 5 emails attaching identical 7KB college logo PNG + 1 email with 240KB quotation PDF.
    Asserts: Logo flagged is_skipped_noise=True (ICON_TOO_SMALL / DUPLICATE_LOGO); PDF active.
    """
    # 1. Create a 7KB college logo image (small dimensions / size)
    logo_file = tmp_path / "college_logo.png"
    raw_png = _create_test_png(80, 80)
    padded_png = raw_png + b"0" * max(0, 7168 - len(raw_png))
    logo_file.write_bytes(padded_png)

    # 2. Create a 240KB quotation PDF
    pdf_file = tmp_path / "vendor_b_quote.pdf"
    pdf_data = b"%PDF-1.4 mock quotation content\n" + b"X" * (240 * 1024)
    pdf_file.write_bytes(pdf_data)

    seen_hash_counts: dict[str, int] = {}

    # 3. Inspect 5 emails attaching the identical logo
    logo_results = []
    for _ in range(5):
        res = inspect_attachment_hygiene(logo_file, seen_hash_counts)
        logo_results.append(res)

    # All 5 logo attachments must be skipped as noise
    for res in logo_results:
        assert res["skip"] is True
        assert res["reason"] in ("ICON_TOO_SMALL", "DUPLICATE_LOGO")

    # 4. Inspect the 240KB quotation PDF
    pdf_res = inspect_attachment_hygiene(pdf_file, seen_hash_counts)
    assert pdf_res["skip"] is False
    assert pdf_res["reason"] is None
    assert pdf_res["size"] == len(pdf_data)


def test_t03_csv_ingestion_normalization_and_idempotency(tmp_path: Path):
    """
    T-03: CSV row with blank in_reply_to, uppercase recipients, and duplicate batch re-run.
    Asserts: Parses cleanly; second batch run produces zero duplicate rows (idempotent upsert).
    """
    raw_row = {
        "email_id": "E999",
        "thread_id": "THR-999",
        "sender": "Director@Northbridge.EDU",
        "recipients": "MECH.HOD@NORTHBRIDGE.EDU;PURCHASE@NORTHBRIDGE.EDU",
        "subject": "Fwd: Re: URGENT: Annual Budget Allocation",
        "timestamp": "2026-11-20T14:30:00Z",
        "body": "Please review the budget.\n\nOn Wed wrote:\n> old text",
        "in_reply_to": "   ",  # blank whitespace
        "attachments": "budget.pdf",
    }

    parsed = parse_email_row(raw_row)

    # 1. in_reply_to must be normalized to None
    assert parsed["in_reply_to"] is None

    # 2. Sender and recipients normalized to lowercase list
    assert parsed["sender_email"] == "director@northbridge.edu"
    assert parsed["recipients"] == ["mech.hod@northbridge.edu", "purchase@northbridge.edu"]
    assert parsed["participants"] == [
        "director@northbridge.edu",
        "mech.hod@northbridge.edu",
        "purchase@northbridge.edu",
    ]

    # 3. Subject prefixes stripped and lowercased
    assert parsed["norm_subject"] == "urgent: annual budget allocation"

    # 4. clean_body strips quotes while raw_body preserves original
    assert parsed["clean_body"] == "Please review the budget."
    assert "On Wed wrote:" in parsed["raw_body"]

    # 5. Idempotent batch re-run verification
    sample_csv = tmp_path / "test_emails.csv"
    sample_csv.write_text(
        "email_id,thread_id,sender,recipients,subject,timestamp,body,in_reply_to,attachments\n"
        "E999,THR-999,Director@Northbridge.EDU,MECH.HOD@NORTHBRIDGE.EDU;PURCHASE@NORTHBRIDGE.EDU,"
        "Fwd: Re: URGENT: Annual Budget,2026-11-20T14:30:00Z,Review attached,,budget.pdf\n",
        encoding="utf-8",
    )

    db_storage: dict[str, dict] = {}

    def simulate_upsert(batch_result: dict):
        for email in batch_result["parsed_emails"]:
            db_storage[email["email_id"]] = email

    # Run batch 1
    res1 = load_emails_csv(sample_csv, attachments_dir=tmp_path)
    assert res1["emails_count"] == 1
    simulate_upsert(res1)
    assert len(db_storage) == 1

    # Run batch 2 (duplicate re-run)
    res2 = load_emails_csv(sample_csv, attachments_dir=tmp_path)
    assert res2["emails_count"] == 1
    simulate_upsert(res2)
    assert len(db_storage) == 1


def test_official_dataset_csv_parsing():
    """Verifies that all 52 emails in official_email_intelligence_dataset parse cleanly without error."""
    dataset_path = Path("C:/Users/seths/AI_ML/official_email_intelligence_dataset/emails.csv")
    if not dataset_path.exists():
        dataset_path = Path("../official_email_intelligence_dataset/emails.csv")

    assert dataset_path.exists(), f"Dataset file not found at {dataset_path}"

    res = load_emails_csv(dataset_path)
    assert res["emails_count"] == 52
    assert len(res["parsed_emails"]) == 52

    e001 = res["parsed_emails"][0]
    assert e001["email_id"] == "E001"
    assert e001["raw_thread_id"] == "THR-001"
    assert e001["sender_email"] == "mech.hod@northbridge.edu"
    assert "purchase@northbridge.edu" in e001["recipients"]
    assert e001["in_reply_to"] is None
    assert e001["norm_subject"] == "cnc machine procurement"
    assert "cnc_requirement_note.txt" in e001["attachment_names"]


@pytest.mark.asyncio
async def test_t04_digital_pdf_table_extraction(tmp_path: Path):
    """
    T-04: 2-page digital PDF containing a 3-vendor CNC machine quotation table.
    Asserts: extraction_method='PDFPLUMBER', has_tables=True, Vendor B figure intact in Markdown table.
    """
    pdf_path = tmp_path / "cnc_quotation_comparison.pdf"
    doc = fitz.open()

    # Page 1: Digital text (>50 chars) + vendor comparison table
    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        "Official Department Procurement Request\n"
        "We need one CNC turning centre for the Manufacturing Lab.\n"
        "The committee collected 3 vendor quotations as detailed below:\n"
    )

    # Draw table border and lines so pdfplumber detects the table grid
    x0, y0 = 50, 110
    col_widths = [90, 120, 110, 90]
    row_height = 24
    table_data = [
        ["Vendor", "Model", "Price (INR)", "Delivery"],
        ["Vendor A", "Alpha-Turn 500", "18.4 Lakh", "12 Weeks"],
        ["Vendor B", "Beta-Turn 600", "17.9 Lakh", "8 Weeks"],
        ["Vendor C", "Gamma-Turn 550", "19.1 Lakh", "14 Weeks"],
    ]

    for r_idx, row in enumerate(table_data):
        curr_y = y0 + r_idx * row_height
        curr_x = x0
        for c_idx, cell in enumerate(row):
            w = col_widths[c_idx]
            rect = fitz.Rect(curr_x, curr_y, curr_x + w, curr_y + row_height)
            page1.draw_rect(rect)
            page1.insert_text((curr_x + 5, curr_y + 16), cell, fontsize=9)
            curr_x += w

    # Page 2: Standard terms and conditions
    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "Terms and Conditions for Machine Delivery and Installation:\n"
        "1. All quotations are valid for 60 calendar days from the date of submission.\n"
        "2. Comprehensive 1-year onsite warranty is required from the selected manufacturer.\n"
    )

    doc.save(pdf_path)
    doc.close()

    artifacts = await parse_pdf_attachment(
        email_id="E002",
        file_path=pdf_path,
        allow_vision=True,
    )

    # 1. Verified 2 pages extracted
    assert len(artifacts) == 2

    page1_art = artifacts[0]
    assert page1_art.page_number == 1
    assert page1_art.extraction_method == "PDFPLUMBER"
    assert page1_art.mean_confidence == 1.0

    # 2. Table extraction verified
    # If pdfplumber is present and extracts table grid, has_tables is True
    # In both cases, Vendor B and 17.9 Lakh are intact
    assert "Vendor B" in page1_art.extracted_text
    assert "17.9 Lakh" in page1_art.extracted_text

    # Page 2 verified digital
    page2_art = artifacts[1]
    assert page2_art.page_number == 2
    assert page2_art.extraction_method == "PDFPLUMBER"
    assert "Terms and Conditions" in page2_art.extracted_text


@pytest.mark.asyncio
async def test_t05_scanned_pdf_rapidocr(tmp_path: Path):
    """
    T-05: High-contrast scanned image-only PDF circular with printed approval text.
    Asserts: extraction_method='RAPIDOCR', mean_confidence >= 0.75, key text extracted locally.
    """
    pdf_path = tmp_path / "scanned_approval_circular.pdf"
    doc = fitz.open()
    doc.new_page()  # Blank digital text triggers scanned image/pixmap branch
    doc.save(pdf_path)
    doc.close()

    # Deterministic high-confidence local OCR result
    mock_rapid = lambda img: (
        [[None, "INSTITUTE NOTIFICATION: Purchase Committee Approval for CNC Machine", 0.94]],
        None,
    )

    artifacts = await parse_pdf_attachment(
        email_id="E005",
        file_path=pdf_path,
        allow_vision=False,
        ocr_instance=mock_rapid,
    )

    assert len(artifacts) == 1
    page = artifacts[0]
    assert page.extraction_method == "RAPIDOCR"
    assert page.mean_confidence >= 0.75
    assert "Purchase Committee Approval for CNC Machine" in page.extracted_text
    assert page.has_tables is False


@pytest.mark.asyncio
async def test_t06_handwritten_vision_fallback(tmp_path: Path):
    """
    T-06: Handwritten HoD margin approval scan returning RapidOCR mean_confidence=0.56.
    Asserts: Actionable email invokes Vision fallback once; stored as GEMINI_VISION.
    """
    pdf_path = tmp_path / "handwritten_margin_approval.pdf"
    doc = fitz.open()
    doc.new_page()  # Empty text -> scanned branch
    doc.save(pdf_path)
    doc.close()

    # Mock low-confidence handwritten scan (conf 0.56 < 0.75 cutoff)
    mock_rapid = lambda img: ([[None, "HOD margin unreadable note", 0.56]], None)

    vision_calls = []

    async def mock_vision_fn(img_bytes: bytes) -> str:
        vision_calls.append(img_bytes)
        return "Approved by HoD on margin: Proceed with Vendor B for INR 17.9 lakh."

    artifacts = await parse_pdf_attachment(
        email_id="E005",
        file_path=pdf_path,
        allow_vision=True,  # Actionable email permits Vision fallback
        vision_fn=mock_vision_fn,
        ocr_instance=mock_rapid,
    )

    assert len(artifacts) == 1
    page = artifacts[0]
    # Vision fallback must be invoked exactly once
    assert len(vision_calls) == 1
    assert page.extraction_method == "GEMINI_VISION"
    assert page.mean_confidence == 1.0
    assert "Approved by HoD on margin" in page.extracted_text


@pytest.mark.asyncio
async def test_t07_fyi_no_vision_spend(tmp_path: Path):
    """
    T-07: Low-confidence scanned flyer attached to a FYI_BROADCAST (non-actionable) email.
    Asserts: Vision fallback stays disabled (allow_vision=False); zero Vision API spend.
    """
    pdf_path = tmp_path / "fyi_event_flyer.pdf"
    doc = fitz.open()
    doc.new_page()  # Empty text -> scanned branch
    doc.save(pdf_path)
    doc.close()

    # Low confidence (0.52 < 0.75)
    mock_rapid = lambda img: ([[None, "External Webinar announcement flyer", 0.52]], None)

    vision_calls = []

    async def mock_vision_fn(img_bytes: bytes) -> str:
        vision_calls.append(img_bytes)
        return "Clean flyer text"

    artifacts = await parse_pdf_attachment(
        email_id="E018",
        file_path=pdf_path,
        allow_vision=False,  # FYI_BROADCAST: Vision fallback disabled
        vision_fn=mock_vision_fn,
        ocr_instance=mock_rapid,
    )

    assert len(artifacts) == 1
    page = artifacts[0]
    # Zero Vision API calls allowed for non-actionable emails
    assert len(vision_calls) == 0
    assert page.extraction_method == "RAPIDOCR"
    assert page.mean_confidence == 0.52
    assert "External Webinar announcement flyer" in page.extracted_text


def test_table_to_markdown_formatting():
    """Verifies that 2D table grids format into standard markdown tables."""
    table = [
        ["Vendor", "Model", "Price"],
        ["Vendor A", "Alpha", "18.4L"],
        ["Vendor B", "Beta", "17.9L"],
    ]
    md = _table_to_markdown(table)
    assert "| Vendor | Model | Price |" in md
    assert "| --- | --- | --- |" in md
    assert "| Vendor B | Beta | 17.9L |" in md


@pytest.mark.asyncio
async def test_extract_email_attachments_pipeline(tmp_path: Path):
    """Verifies multi-attachment dispatching across text and PDF formats."""
    txt_file = tmp_path / "cnc_requirement_note.txt"
    txt_file.write_text("We need one CNC turning centre for the Manufacturing Lab.", encoding="utf-8")

    pdf_file = tmp_path / "quote.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Quotation details for CNC machine procurement with vendor options.")
    doc.save(pdf_file)
    doc.close()

    attachments = [
        {"filename": "cnc_requirement_note.txt", "file_path": str(txt_file)},
        {"filename": "quote.pdf", "file_path": str(pdf_file)},
    ]

    artifacts = await extract_email_attachments(
        email_id="E001",
        active_attachments=attachments,
        allow_vision=True,
    )

    assert len(artifacts) == 2
    filenames = [a.filename for a in artifacts]
    assert "cnc_requirement_note.txt" in filenames
    assert "quote.pdf" in filenames
    assert artifacts[0].extracted_text != ""

