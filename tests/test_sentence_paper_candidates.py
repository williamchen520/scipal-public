"""S2.3: paper-level candidate helpers."""

from __future__ import annotations

import unittest

from services.search.sentence_hybrid import SentenceHybridRetriever


class _FakePG:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "FROM papers" in sql:
            return _Rows([{"paper_id": "p1", "rank": 1.0}])
        return _Rows([{"para_id": "p1_para", "rank": 1.0}])


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class PaperCandidateTests(unittest.TestCase):
    def test_paper_ids(self) -> None:
        pg = _FakePG()
        self.assertEqual(
            SentenceHybridRetriever._paper_candidates(pg, "mouse neurons", 5),
            ["p1"],
        )

    def test_paragraph_ids(self) -> None:
        pg = _FakePG()
        self.assertEqual(
            SentenceHybridRetriever._paragraphs_for_paper(pg, "p1", "mouse", 3),
            ["p1_para"],
        )


if __name__ == "__main__":
    unittest.main()
