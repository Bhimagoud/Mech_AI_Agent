"""
Service: Document Ingestor
Responsibility: Extract PEOs and Department Mission (DM) statements from
uploaded PDF or DOCX files using text parsing heuristics.
"""

import re
import io
import logging
from pathlib import Path

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_document(file_bytes: bytes, filename: str) -> dict:
    """
    Parse an uploaded document and return a structured dict with:
        {
            "peos": [{"id": "PEO1", "text": "..."}, ...],
            "missions": [{"id": "DM1", "text": "..."}, ...],
            "raw_text": "...",
            "source": filename
        }
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        raw_text = _extract_pdf_text(file_bytes)
    elif ext in (".docx", ".doc"):
        raw_text = _extract_docx_text(file_bytes)
    else:
        raw_text = file_bytes.decode("utf-8", errors="replace")

    peos = _parse_peos(raw_text)
    missions = _parse_missions(raw_text)

    return {
        "peos": peos,
        "missions": missions,
        "raw_text": raw_text[:8000],   # cap for downstream context
        "full_text": raw_text,
        "source": filename,
    }


def build_context_from_manual(file_bytes: bytes, filename: str) -> str:
    """
    Extract the scoring rubric / evaluation guidelines from an NBA manual PDF.
    Returns a compact text snippet to be injected into agent prompts.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        raw = _extract_pdf_text(file_bytes)
    else:
        raw = file_bytes.decode("utf-8", errors="replace")

    # Pull the section about correlation levels / scoring
    snippet = _extract_scoring_section(raw)
    return snippet


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_pdf_text(file_bytes: bytes) -> str:
    if not PDF_AVAILABLE:
        raise RuntimeError("pdfplumber not installed")
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


def _extract_docx_text(file_bytes: bytes) -> str:
    if not DOCX_AVAILABLE:
        raise RuntimeError("python-docx not installed")
    doc = DocxDocument(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


# ---------------------------------------------------------------------------
# PEO / Mission parsers
# ---------------------------------------------------------------------------

_PEO_PATTERNS = [
    # "PEO 1.", "PEO1:", "PEO-1." — must be at start of line or after newline
    re.compile(
        r"(?:^|\n)PEO[\s\-_]*(\d+)[.\s:\-]+(.+?)(?=\nPEO[\s\-_]*\d+|\nDM\s*\d+|$)",
        re.IGNORECASE | re.DOTALL,
    ),
]

_MISSION_PATTERNS = [
    # "DM1.", "DM 1:"
    re.compile(
        r"DM[\s\-_]*(\d+)[.\s:\-]+(.+?)(?=DM[\s\-_]*\d+|PEO|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "Mission 1:", "M1."
    re.compile(
        r"(?:Mission[\s\-_]*)(\d+)[.\s:\-]+(.+?)(?=(?:Mission[\s\-_]*)\d+|PEO|$)",
        re.IGNORECASE | re.DOTALL,
    ),
]


def _parse_peos(text: str) -> list:
    """Return list of {"id": "PEO1", "text": "..."} dicts."""
    results = []
    seen_ids = set()

    for pattern in _PEO_PATTERNS:
        for m in pattern.finditer(text):
            idx = m.group(1).strip()
            body = _clean(m.group(2))
            if not body or idx in seen_ids:
                continue
            # Skip if body looks like navigation / header noise
            if len(body) < 20:
                continue
            peo_id = f"PEO{idx}"
            seen_ids.add(idx)
            results.append({"id": peo_id, "text": body})

    # Sort by numeric id
    results.sort(key=lambda x: int(re.search(r"\d+", x["id"]).group()))
    return results


def _parse_missions(text: str) -> list:
    """Return list of {"id": "DM1", "text": "..."} dicts."""
    results = []
    seen_ids = set()

    for pattern in _MISSION_PATTERNS:
        for m in pattern.finditer(text):
            idx = m.group(1).strip()
            body = _clean(m.group(2))
            if not body or idx in seen_ids:
                continue
            if len(body) < 20:
                continue
            dm_id = f"DM{idx}"
            seen_ids.add(idx)
            results.append({"id": dm_id, "text": body})

    results.sort(key=lambda x: int(re.search(r"\d+", x["id"]).group()))
    return results


def _extract_scoring_section(text: str) -> str:
    """Grab the correlation-level definitions from an NBA manual."""
    match = re.search(
        r"(1[\s:]+Slight.*?3[\s:]+Substantial.*?\n)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1)[:600]

    # Fallback: grab lines around "correlation"
    lines = text.splitlines()
    hits = [
        i for i, l in enumerate(lines)
        if "correlation" in l.lower() or "slight" in l.lower()
    ]
    if hits:
        start = max(0, hits[0] - 2)
        end = min(len(lines), hits[0] + 15)
        return "\n".join(lines[start:end])

    return "1: Slight, 2: Moderate, 3: Substantial (per NBA UG Tier-I Manual)"


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    """Strip excess whitespace and newlines from extracted text."""
    s = re.sub(r"\s+", " ", s).strip()
    # Remove trailing noise like page numbers
    s = re.sub(r"\s*\d{1,3}\s*$", "", s).strip()
    return s
