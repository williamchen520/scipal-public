"""D4 abstract-only paper and full-text upgrade tests."""

from __future__ import annotations

import os
import unittest
import uuid

import psycopg

from services.imports.paper_build import build_paper, paper_id_for
from services.online.abstract_paper import ensure_abstract_paper


def _dsn() -> str:
    return os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()


def _cleanup(paper_id: str) -> None:
    with psycopg.connect(_dsn()) as conn:
        conn.execute("DELETE FROM paper_reviews WHERE paper_id=%s", (paper_id,))
        conn.execute("DELETE FROM sentences WHERE paper_id=%s", (paper_id,))
        conn.execute("DELETE FROM paragraphs WHERE paper_id=%s", (paper_id,))
        conn.execute("DELETE FROM paper_sources WHERE paper_id=%s", (paper_id,))
        conn.execute("DELETE FROM paper_external_ids WHERE paper_id=%s", (paper_id,))
        conn.execute("DELETE FROM papers WHERE paper_id=%s", (paper_id,))
        conn.commit()


class PaperOverrideTests(unittest.TestCase):
    def test_override_wins(self) -> None:
        self.assertEqual(
            paper_id_for({"paper_id_override": "paper_existing", "source_kind": "html"}),
            "paper_existing",
        )


@unittest.skipUnless(_dsn(), "PostgreSQL DSN not configured")
class AbstractPaperTests(unittest.TestCase):
    def test_abstract_then_fulltext_upgrade(self) -> None:
        source = "test"
        external = "ABS:" + uuid.uuid4().hex[:10]
        candidate = {
            "source": source,
            "external_id": external,
            "doi": f"10.1000/{external}",
            "title": "Abstract only test",
            "abstract": "A short abstract for the test.",
            "authors": ["A. Author"],
            "year": "2026",
            "journal": "Test",
        }
        result = ensure_abstract_paper(candidate, dsn=_dsn())
        paper_id = result["paper_id"]
        self.assertFalse(result["already_fulltext"])
        try:
            with psycopg.connect(_dsn()) as conn:
                row = conn.execute(
                    "SELECT acquisition,total_paragraphs FROM papers WHERE paper_id=%s",
                    (paper_id,),
                ).fetchone()
                sentences = conn.execute(
                    "SELECT count(*) FROM sentences WHERE paper_id=%s", (paper_id,)
                ).fetchone()[0]
            self.assertEqual(row[0], "abstract")
            self.assertEqual(row[1], 0)
            self.assertEqual(sentences, 0)

            payload = {
                "title": "Abstract only test",
                "doi": candidate["doi"],
                "abstract": "A short abstract for the test.",
                "sections": [
                    {"title": "Results", "paragraphs": [f"paragraph {i} " + "x" * 200 for i in range(5)]}
                ],
            }
            build_paper(
                paper_id,
                payload,
                source_kind="html",
                source_uri="https://example.org/fulltext",
                dsn=_dsn(),
            )
            with psycopg.connect(_dsn()) as conn:
                row = conn.execute(
                    "SELECT acquisition,total_paragraphs FROM papers WHERE paper_id=%s",
                    (paper_id,),
                ).fetchone()
                review = conn.execute(
                    "SELECT status FROM paper_reviews WHERE paper_id=%s", (paper_id,)
                ).fetchone()[0]
            self.assertEqual(row[0], "fulltext")
            self.assertGreater(row[1], 0)
            self.assertEqual(review, "draft")
        finally:
            _cleanup(paper_id)


if __name__ == "__main__":
    unittest.main()
