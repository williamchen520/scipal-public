"""D0: local and online search buckets must not be score-merged."""

from __future__ import annotations

import unittest
from unittest import mock

from services.search.hybrid_retriever import HybridRetriever


class SearchBucketTests(unittest.TestCase):
    def test_local_and_online_are_separate(self) -> None:
        retriever = object.__new__(HybridRetriever)
        retriever.use_online = True
        retriever.online_searcher = object()
        retriever.online_max_results = 10
        retriever.use_protocols_io = False
        retriever.protocols_io_client = None
        retriever.protocols_io_max_results = 0
        retriever.verbose = False
        local = [
            {"paper_id": "local_1", "doi": "10.1/local", "score": 0.1},
            {"paper_id": "local_1_dup", "doi": "10.1/local", "score": 0.05},
        ]
        online = [
            {"paper_id": "online_1", "doi": "10.1/online", "score": 0.99, "in_local_db": False},
            {"paper_id": "online_2", "doi": "10.1/online2", "score": 0.98, "in_local_db": False},
        ]
        with mock.patch.object(retriever, "_search_local", return_value=local), mock.patch.object(
            retriever, "_search_online", return_value=online
        ):
            result = retriever.search_papers("q", top_k=10, use_online=True)
        self.assertEqual([row["paper_id"] for row in result["papers"]], ["local_1"])
        self.assertEqual(
            [row["paper_id"] for row in result["online_papers"]],
            ["online_1", "online_2"],
        )
        self.assertEqual(result["local_total"], 1)
        self.assertEqual(result["online_total"], 2)
        self.assertEqual(result["total"], 3)
        self.assertNotIn("online_1", [row["paper_id"] for row in result["papers"]])


if __name__ == "__main__":
    unittest.main()
