# backend/app/pipeline/hygiene.py
import hashlib
import re
from pathlib import Path
from typing import Union
try:
    from PIL import Image
    def _get_image_dimensions(data: bytes) -> tuple[int, int]:
        import io
        with Image.open(io.BytesIO(data)) as img:
            return img.size
except ImportError:
    import fitz
    def _get_image_dimensions(data: bytes) -> tuple[int, int]:
        pm = fitz.Pixmap(data)
        return pm.width, pm.height
from app.config import settings

QUOTE_MARKERS = [
    re.compile(r"^On .+ wrote:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^From:\s+.+\nSent:\s+.+$", re.IGNORECASE | re.MULTILINE),
]
SIG_MARKER = re.compile(r"^--\s*$", re.MULTILINE)
SUBJ_PREFIX = re.compile(r"^(?:(?:re|fwd|fw)\s*:\s*)+", re.IGNORECASE)


def strip_quoted_replies(raw_body: str) -> str:
    """Strips reply chains, headers, signatures, and > quotes, keeping only the new reply."""
    text = (raw_body or "").replace("\r\n", "\n")
    cut_positions = []
    for pattern in QUOTE_MARKERS:
        m = pattern.search(text)
        if m:
            cut_positions.append(m.start())
    sig = SIG_MARKER.search(text)
    if sig:
        cut_positions.append(sig.start())
    if cut_positions:
        text = text[: min(cut_positions)]
    clean_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    return "\n".join(clean_lines).strip()


def normalize_subject(subject: str) -> str:
    """Removes Re:/Fwd: prefixes and normalizes whitespace to lower case."""
    stripped = SUBJ_PREFIX.sub("", subject or "").strip()
    return re.sub(r"\s+", " ", stripped).lower()


def inspect_attachment_hygiene(
    file_path: Union[Path, str],
    seen_hash_counts: dict[str, int],
    file_bytes: bytes | None = None
) -> dict:
    """
    Evaluates attachment file for noise:
    - Flags images < 15KB or < 150x150px as ICON_TOO_SMALL.
    - Flags images repeated > 3 times by SHA256 as DUPLICATE_LOGO.
    - Preserves PDFs, spreadsheets, and active documents.
    """
    path = Path(file_path)
    if file_bytes is not None:
        data = file_bytes
    elif path.exists() and path.is_file():
        data = path.read_bytes()
    else:
        return {"sha256": "", "size": 0, "skip": True, "reason": "FILE_NOT_FOUND"}

    sha = hashlib.sha256(data).hexdigest()
    size_bytes = len(data)
    ext = path.suffix.lower()
    seen_hash_counts[sha] = seen_hash_counts.get(sha, 0) + 1

    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        if size_bytes < settings.min_image_bytes:
            return {"sha256": sha, "size": size_bytes, "skip": True, "reason": "ICON_TOO_SMALL"}
        try:
            w, h = _get_image_dimensions(data)
            if w < settings.min_image_px or h < settings.min_image_px:
                return {"sha256": sha, "size": size_bytes, "skip": True, "reason": "ICON_TOO_SMALL"}
        except Exception:
            return {"sha256": sha, "size": size_bytes, "skip": True, "reason": "ICON_TOO_SMALL"}

        if seen_hash_counts[sha] > 3:
            return {"sha256": sha, "size": size_bytes, "skip": True, "reason": "DUPLICATE_LOGO"}

    return {"sha256": sha, "size": size_bytes, "skip": False, "reason": None}
