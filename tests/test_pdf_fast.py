"""PDF text fast-path tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz

from services.papers.pdf_fast import try_extract


def _make_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        text = (
            f"Abstract\nThis is test page {index + 1}. " + ("A" * 700)
            + "\n\nIntroduction\n" + ("B" * 500)
        )
        page.insert_textbox(fitz.Rect(50, 50, 550, 780), text, fontsize=10)
    doc.save(path)
    doc.close()


class PdfFastTests(unittest.TestCase):
    def test_text_pdf_extracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "text.pdf"
            _make_pdf(path)
            result = try_extract(path)
        self.assertIsNotNone(result)
        self.assertEqual(result["parse_engine"], "pymupdf-fast")
        self.assertGreaterEqual(len(result["sections"]), 1)

    def test_short_pdf_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "short.pdf"
            doc = fitz.open()
            doc.new_page().insert_text((50, 72), "short", fontsize=10)
            doc.save(path)
            doc.close()
            self.assertIsNone(try_extract(path))


if __name__ == "__main__":
    unittest.main()
