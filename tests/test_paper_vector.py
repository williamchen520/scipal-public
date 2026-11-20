"""S2.3b: paper vector adapter test."""

from __future__ import annotations

import unittest

from services.search.paper_vector import PaperVectorSearch


class _Rows:
    def fetchall(self):
        return [{"paper_id": "p1", "rank": 0.9}]


class _Conn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Rows()

    def close(self):
        pass


class PaperVectorTests(unittest.TestCase):
    def test_search(self) -> None:
        conn = _Conn()
        search = PaperVectorSearch(connector=lambda: conn)
        hits = search.search([0.1, 0.2], top_k=3)
        self.assertEqual(hits[0]["paper_id"], "p1")
        self.assertIn("paper_embeddings", conn.calls[-1][0])


if __name__ == "__main__":
    unittest.main()
