"""D5 search bridge tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.online import search_bridge


class SearchBridgeTests(unittest.TestCase):
    def test_pmc_and_pubmed_enqueue(self) -> None:
        rows = [
            {"source": "online_pmc", "pmcid": "PMC1", "title": "A", "doi": "10.1/a", "in_local_db": False},
            {"source": "online_pubmed", "pmid": "2", "title": "B", "doi": "10.1/b", "in_local_db": False},
            {"source": "online_pmc", "pmcid": "PMC3", "title": "C", "in_local_db": True},
        ]
        with mock.patch.object(
            search_bridge.candidates, "create_run", return_value="run_1"
        ), mock.patch.object(
            search_bridge.candidates,
            "count_created_today",
            return_value=0,
        ), mock.patch.object(
            search_bridge.candidates,
            "upsert_candidate",
            side_effect=lambda **kwargs: {
                "candidate_id": "cand_" + kwargs["external_id"],
                "ingest_status": "queued",
                "local_paper_id": "",
            },
        ) as upsert:
            result = search_bridge.enqueue_online_results(rows, query="q", top_n=2)
        self.assertEqual(result["run_id"], "run_1")
        self.assertEqual(len(result["candidates"]), 2)
        pmc = upsert.call_args_list[0].kwargs
        self.assertEqual(pmc["source"], "pmc")
        self.assertIn("PMC1", pmc["url"])
        pubmed = upsert.call_args_list[1].kwargs
        self.assertEqual(pubmed["source"], "pubmed")
        self.assertEqual(pubmed["url"], "")

    def test_daily_budget_skips(self) -> None:
        rows = [
            {"source": "online_pmc", "pmcid": "PMC1", "title": "A", "in_local_db": False}
        ]
        with mock.patch.object(
            search_bridge.candidates, "count_created_today", return_value=20
        ), mock.patch.object(
            search_bridge.candidates, "create_run"
        ) as create:
            result = search_bridge.enqueue_online_results(rows, query="q", top_n=3)
        self.assertEqual(result["skipped"], "daily_budget")
        create.assert_not_called()

    def test_no_new_hits(self) -> None:
        self.assertEqual(
            search_bridge.enqueue_online_results(
                [{"source": "online_pmc", "pmcid": "PMC1", "in_local_db": True}],
                query="q",
            ),
            {"run_id": "", "candidates": []},
        )


if __name__ == "__main__":
    unittest.main()
