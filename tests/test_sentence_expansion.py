"""S2.1: sentence query-variant selection tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.search.sentence_hybrid import SentenceHybridRetriever


class SentenceQueryVariantsTests(unittest.TestCase):
    def test_disabled_returns_original(self) -> None:
        retriever = object.__new__(SentenceHybridRetriever)
        retriever.expand_queries = False
        retriever.query_expander = None
        self.assertEqual(retriever._query_variants("a b"), ["a b"])

    def test_enabled_dedupes_and_caps(self) -> None:
        retriever = object.__new__(SentenceHybridRetriever)
        retriever.expand_queries = True
        retriever.max_query_variants = 3
        retriever.query_expander = mock.Mock()
        retriever.query_expander.expand.return_value = [
            "a b", "a b", "a c", "a d", "a e"
        ]
        self.assertEqual(retriever._query_variants("a b"), ["a b", "a c", "a d"])

    def test_expander_failure_returns_original(self) -> None:
        retriever = object.__new__(SentenceHybridRetriever)
        retriever.expand_queries = True
        retriever.max_query_variants = 3
        retriever.query_expander = mock.Mock()
        retriever.query_expander.expand.side_effect = RuntimeError("boom")
        self.assertEqual(retriever._query_variants("a b"), ["a b"])


if __name__ == "__main__":
    unittest.main()
