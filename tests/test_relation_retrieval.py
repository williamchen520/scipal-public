from __future__ import annotations

import unittest

from scripts.relation_retrieval import build_channels, rank_related, rrf


EDGES = [
    ("A", "B"),
    ("A", "C"),
    ("D", "A"),
    ("D", "E"),
    ("F", "B"),
    ("F", "C"),
]


class RelationRetrievalTest(unittest.TestCase):
    def test_channels(self):
        channels = build_channels("A", EDGES)
        self.assertEqual(set(channels["out_citation"]), {"B", "C"})
        self.assertEqual(channels["in_citation"], ["D"])
        self.assertEqual(channels["co_citation"], ["E"])
        self.assertEqual(channels["bibliographic_coupling"], ["F"])

    def test_related_candidates_include_coupling(self):
        ranked = rank_related("A", EDGES, limit=10)
        by_id = {row["paper_id"]: row for row in ranked}
        self.assertIn("F", by_id)
        self.assertTrue(by_id["F"]["evidence"]["bibliographic_coupling"])

    def test_empty_seed(self):
        self.assertEqual(rank_related("Z", EDGES), [])

    def test_rrf_ties_are_stable(self):
        scores = rrf({"x": ["a", "b"], "y": ["b", "a"]})
        self.assertGreaterEqual(scores["a"], scores["b"])


if __name__ == "__main__":
    unittest.main()
