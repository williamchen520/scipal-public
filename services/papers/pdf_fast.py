"""PDF text fast path: PyMuPDF for born-digital PDFs, Docling fallback."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pymupdf as fitz

from build_db.parsers.pdf_metadata import extract_pdf_title

MIN_CHARS = 1000
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def _blocks(page: fitz.Page) -> list[str]:
    out = []
    for block in page.get_text("blocks"):
        text = _clean(str(block[4] or ""))
        if len(text) >= 20:
            out.append(text)
    return out


def _abstract(text: str) -> str:
    match = re.search(
        r"(?:^|\n)\s*(?:Abstract|ABSTRACT)\s*\n?(.+?)(?=\n\s*(?:Introduction|INTRODUCTION|Background|BACKGROUND|Keywords|KEYWORDS)\b)",
        text,
        flags=re.S,
    )
    if match:
        return _clean(match.group(1))[:4000]
    return ""


def try_extract(path: str | Path) -> dict[str, Any] | None:
    path = Path(path)
    try:
        doc = fitz.open(path)
    except Exception:
        return None
    pages: list[tuple[int, str, list[str]]] = []
    total = 0
    try:
        for index, page in enumerate(doc, start=1):
            blocks = _blocks(page)
            text = _clean("\n\n".join(blocks))
            total += len(text)
            if len(text) >= 40:
                pages.append((index, text, blocks))
    finally:
        doc.close()
    if total < MIN_CHARS or not pages:
        return None
    all_text = "\n\n".join(item[1] for item in pages)
    title = extract_pdf_title(path) or path.stem
    doi_match = DOI_RE.search(all_text[:8000])
    sections = [
        {"title": f"Page {index}", "paragraphs": blocks}
        for index, _text, blocks in pages
    ]
    return {
        "title": title,
        "doi": doi_match.group(0) if doi_match else "",
        "abstract": _abstract(all_text),
        "sections": sections,
        "parse_engine": "pymupdf-fast",
        "text_chars": total,
    }
