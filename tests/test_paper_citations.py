"""B4 external IDs, citation queries, and enrichment tests."""

from __future__ import annotations

import os
import unittest
import uuid
from unittest import mock

import psycopg

from services.papers import citations, enrich, external_ids


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


@unittest.skipUnless(_dsn(), "PostgreSQL DSN not configured")
class CitationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dsn = _dsn()
        suffix = uuid.uuid4().hex[:10]
        self.p1 = f"paper_b4_{suffix}_src"
        self.p2 = f"paper_b4_{suffix}_dst"
        self.doi1 = f"10.1000/b4.{suffix}.src"
        self.doi2 = f"10.1000/b4.{suffix}.dst"
        with psycopg.connect(self.dsn) as conn:
            for paper_id, doi, title in (
                (self.p1, self.doi1, "B4 source"),
                (self.p2, self.doi2, "B4 destination"),
            ):
                conn.execute(
                    "INSERT INTO papers (paper_id,title,doi,filename,parse_engine,total_paragraphs) "
                    "VALUES (%s,%s,%s,'','test',1)",
                    (paper_id, title, doi),
                )
            conn.commit()

    def tearDown(self) -> None:
        with psycopg.connect(self.dsn) as conn:
            rows = conn.execute(
                "DELETE FROM paper_citation_edges WHERE src_paper_id IN (%s,%s) "
                "OR dst_paper_id IN (%s,%s) RETURNING edge_id",
                (self.p1, self.p2, self.p1, self.p2),
            ).fetchall()
            for row in rows:
                conn.execute("DELETE FROM cross_paper_index WHERE link_id=%s", (row[0],))
            conn.execute(
                "DELETE FROM paper_external_ids WHERE paper_id IN (%s,%s)",
                (self.p1, self.p2),
            )
            conn.execute("DELETE FROM papers WHERE paper_id IN (%s,%s)", (self.p1, self.p2))
            conn.commit()

    def test_external_id_idempotent(self) -> None:
        first = external_ids.upsert_external_id(
            paper_id=self.p1, source="doi", external_id=self.doi1.upper(), dsn=self.dsn
        )
        second = external_ids.upsert_external_id(
            paper_id=self.p1, source="doi", external_id=self.doi1, dsn=self.dsn
        )
        self.assertEqual(first["external_id"], self.doi1)
        self.assertEqual(second["external_id"], self.doi1)
        self.assertEqual(len(external_ids.list_external_ids(self.p1, dsn=self.dsn)), 1)

    def test_enrich_edges_and_queries(self) -> None:
        with mock.patch(
            "services.papers.enrich.metadata_sources.openalex_work",
            return_value={"id": "https://openalex.org/W1", "referenced_works": ["W2"]},
        ), mock.patch(
            "services.papers.enrich.metadata_sources.openalex_resolve_ids",
            return_value={"W2": self.doi2},
        ), mock.patch(
            "services.papers.enrich.metadata_sources.openalex_cited_by",
            return_value=[
                {"id": "W3", "doi": self.doi2, "title": "Citing", "year": 2026}
            ],
        ):
            result = enrich.enrich_paper(self.p1, dsn=self.dsn)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["external_ids"], 2)
        self.assertEqual(result["references"], 1)
        self.assertEqual(result["citations"], 1)
        self.assertEqual(len(citations.list_references(self.p1, dsn=self.dsn)), 1)
        self.assertEqual(len(citations.list_citations(self.p1, dsn=self.dsn)), 1)

    def test_enrich_idempotent(self) -> None:
        patches = [
            mock.patch(
                "services.papers.enrich.metadata_sources.openalex_work",
                return_value={"id": "https://openalex.org/W1", "referenced_works": ["W2"]},
            ),
            mock.patch(
                "services.papers.enrich.metadata_sources.openalex_resolve_ids",
                return_value={"W2": self.doi2},
            ),
            mock.patch(
                "services.papers.enrich.metadata_sources.openalex_cited_by",
                return_value=[],
            ),
        ]
        for patcher in patches:
            patcher.start()
        try:
            enrich.enrich_paper(self.p1, dsn=self.dsn)
            enrich.enrich_paper(self.p1, dsn=self.dsn)
        finally:
            for patcher in patches:
                patcher.stop()
        self.assertEqual(len(citations.list_references(self.p1, dsn=self.dsn)), 1)

    def test_network_failure_does_not_raise(self) -> None:
        with mock.patch(
            "services.papers.enrich.metadata_sources.openalex_work",
            side_effect=RuntimeError("offline"),
        ), mock.patch(
            "services.papers.enrich.metadata_sources.crossref_work",
            side_effect=RuntimeError("offline"),
        ), mock.patch(
            "services.papers.enrich.metadata_sources.openalex_cited_by",
            side_effect=RuntimeError("offline"),
        ):
            result = enrich.enrich_paper(self.p1, dsn=self.dsn)
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])
        self.assertEqual(citations.list_references(self.p1, dsn=self.dsn), [])


if __name__ == "__main__":
    unittest.main()
