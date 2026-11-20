"""S2.3d: separate base/paper quota merge tests."""

from __future__ import annotations

import unittest

from services.search.paper_quota import PaperQuotaRetriever


class PaperQuotaMergeTests(unittest.TestCase):
    def test_paper_inserted_after_base_top8(self) -> None:
        base = [{"sentence_id": f"b{i}", "paper_id": f"pb{i}"} for i in range(18)]
        paper = [{"sentence_id": "p1", "paper_id": "pp1"}, {"sentence_id": "p2", "paper_id": "pp2"}]
        merged = PaperQuotaRetriever.merge(base, paper, top_k=20, quota=2)
        self.assertEqual([u["sentence_id"] for u in merged[:8]], [f"b{i}" for i in range(8)])
        self.assertEqual([u["sentence_id"] for u in merged[8:10]], ["p1", "p2"])
        self.assertEqual(len(merged), 20)

    def test_no_paper_keeps_base(self) -> None:
        base = [{"sentence_id": f"b{i}"} for i in range(10)]
        merged = PaperQuotaRetriever.merge(base, [], top_k=10, quota=2)
        self.assertEqual([u["sentence_id"] for u in merged], [f"b{i}" for i in range(10)])


if __name__ == "__main__":
    unittest.main()
