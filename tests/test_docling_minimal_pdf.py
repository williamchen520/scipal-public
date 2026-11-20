"""Opt-in docling regression: a minimal text PDF must parse.

Run with:
    SCIPAL_DOCLING_TEST=1 python -m unittest tests.test_docling_minimal_pdf
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("SCIPAL_DOCLING_TEST") == "1",
    "set SCIPAL_DOCLING_TEST=1 to run docling integration",
)
class DoclingMinimalPdfTest(unittest.TestCase):
    def test_minimal_pdf_text(self):
        import fitz
        from docling.document_converter import DocumentConverter

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimal.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "STAT1 signaling in immunity")
            page.insert_text((72, 100), "Abstract")
            page.insert_text((72, 120), "STAT1 is a key mediator of interferon signaling.")
            doc.save(str(path))
            doc.close()

            result = DocumentConverter().convert(str(path))
            text = result.document.export_to_markdown()
            self.assertIn("STAT1", text)


if __name__ == "__main__":
    unittest.main()
