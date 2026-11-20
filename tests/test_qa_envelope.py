"""QA performance: envelope must reuse retrieval, not retrieve twice."""

from __future__ import annotations

import unittest
from unittest import mock

from services.search.unified_retriever import UnifiedRetriever


def _env():
    return {
        "route": None,
        "parent_contexts": [],
        "paragraphs": [],
        "summaries": [],
        "chunks": [],
        "figures": [],
        "tables": [],
        "papers": [],
        "abstracts": [],
        "graph_neighbors": [],
    }


class EnvelopeReuseTests(unittest.TestCase):
    def test_to_envelope_calls_retrieve_once(self) -> None:
        retriever = object.__new__(UnifiedRetriever)
        retriever.retrieve = mock.Mock(return_value=_env())
        text = retriever.to_envelope("q")
        self.assertIn("QUERY: q", text)
        retriever.retrieve.assert_called_once()

    def test_envelope_from_result_does_not_retrieve(self) -> None:
        retriever = object.__new__(UnifiedRetriever)
        retriever.retrieve = mock.Mock(side_effect=AssertionError("must not retrieve"))
        text = retriever.envelope_from_result("q", _env())
        self.assertIn("QUERY: q", text)


if __name__ == "__main__":
    unittest.main()
