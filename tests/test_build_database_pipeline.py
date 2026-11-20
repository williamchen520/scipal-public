"""Opt-in legacy build_database pipeline regression.

Run with:
    SCIPAL_DOCLING_TEST=1 python -m unittest tests.test_build_database_pipeline
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("SCIPAL_DOCLING_TEST") == "1",
    "set SCIPAL_DOCLING_TEST=1 to run docling integration",
)
class BuildDatabasePipelineTest(unittest.TestCase):
    def test_minimal_pdf_enters_papers_table(self):
        import fitz
        from build_db.build_database import build_database

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            input_dir = root / "pdfs"
            input_dir.mkdir()
            pdf_path = input_dir / "minimal.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "STAT1 signaling in immunity")
            page.insert_text((72, 100), "Abstract")
            page.insert_text((72, 120), "STAT1 is a key mediator of interferon signaling.")
            doc.save(str(pdf_path))
            doc.close()

            db_path = root / "research.db"
            build_database(str(input_dir), str(db_path), device="cpu")

            conn = sqlite3.connect(str(db_path))
            try:
                papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
                paragraphs = conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(papers, 1)
            self.assertGreater(paragraphs, 0)


if __name__ == "__main__":
    unittest.main()
