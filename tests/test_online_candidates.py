"""D1 online candidate tests."""

from __future__ import annotations

import os
import unittest
import uuid

import psycopg

from services.online import candidates


def _dsn() -> str:
    return os.environ.get("SCIPAL_CORE_DSN", "").strip()


class CandidateUnitTests(unittest.TestCase):
    def test_candidate_id_stable(self) -> None:
        self.assertEqual(
            candidates.candidate_id("pubmed", "PMID:1"),
            candidates.candidate_id("pubmed", "PMID:1"),
        )
        self.assertNotEqual(
            candidates.candidate_id("pubmed", "PMID:1"),
            candidates.candidate_id("pmc", "PMID:1"),
        )


@unittest.skipUnless(_dsn(), "SCIPAL_CORE_DSN not configured")
class CandidateIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dsn = _dsn()
        self.source = "test"
        self.external = "X:" + uuid.uuid4().hex[:10]
        self.run_id = candidates.create_run(
            query_hash=uuid.uuid4().hex, source=self.source, counts={"found": 1}
        )

    def tearDown(self) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "DELETE FROM online_candidates WHERE source=%s AND external_id=%s",
                (self.source, self.external),
            )
            conn.execute("DELETE FROM online_search_runs WHERE run_id=%s", (self.run_id,))
            conn.commit()

    def test_upsert_idempotent_and_status_preserved(self) -> None:
        first = candidates.upsert_candidate(
            run_id=self.run_id,
            source=self.source,
            external_id=self.external,
            title="D1",
            doi="10.1/d1",
        )
        second = candidates.upsert_candidate(
            run_id=self.run_id,
            source=self.source,
            external_id=self.external,
            title="D1 updated",
        )
        self.assertEqual(first["candidate_id"], second["candidate_id"])
        rows = candidates.list_candidates(run_id=self.run_id)
        self.assertEqual(len(rows), 1)
        candidates.mark_status(
            first["candidate_id"], "draft", local_paper_id="paper_test"
        )
        candidates.upsert_candidate(
            run_id=self.run_id,
            source=self.source,
            external_id=self.external,
            title="D1 again",
        )
        row = candidates.list_candidates(run_id=self.run_id)[0]
        self.assertEqual(row["ingest_status"], "draft")
        self.assertEqual(row["local_paper_id"], "paper_test")

    def test_ingest_status_rejects_unknown(self) -> None:
        row = candidates.upsert_candidate(
            run_id=self.run_id,
            source=self.source,
            external_id=self.external,
            title="D1",
        )
        with self.assertRaises(candidates.CandidateError):
            candidates.mark_status(row["candidate_id"], "nonsense")


if __name__ == "__main__":
    unittest.main()
