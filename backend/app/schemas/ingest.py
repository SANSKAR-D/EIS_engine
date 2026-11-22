# backend/app/schemas/ingest.py
from typing import Optional, Literal
from pydantic import BaseModel, Field


class AttachmentPageArtifact(BaseModel):
    email_id: str
    filename: str
    page_number: int
    extraction_method: Literal["PDFPLUMBER", "RAPIDOCR", "GEMINI_VISION"]
    mean_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extracted_text: str
    has_tables: bool = False


class AttachmentArtifact(BaseModel):
    email_id: str
    filename: str
    file_path: str
    file_size_bytes: int = 0
    sha256_hash: str = ""
    is_skipped_noise: bool = False
    skip_reason: Optional[str] = None
    page_count: int = 0
