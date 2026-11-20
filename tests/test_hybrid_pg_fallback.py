"""S2.0: HybridSearch falls back to PG when Chroma is missing."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.search.hybrid_search import HybridSearch


class HybridPgFallbackTests(unittest.TestCase):
    def test_missing_chroma_switches_to_pgvector(self) -> None:
        with mock.patch.dict(
            os.environ, {"SCIPAL_VECTOR_BACKEND": ""}, clear=False
        ), mock.patch(
            "chromadb.PersistentClient", side_effect=RuntimeError("no chroma")
        ), mock.patch(
            "sentence_transformers.SentenceTransformer"
        ):
            searcher = HybridSearch()
            self.assertIsNone(searcher.client)
            self.assertIsNone(searcher.para_collection)
            self.assertEqual(os.environ.get("SCIPAL_VECTOR_BACKEND"), "pgvector")


if __name__ == "__main__":
    unittest.main()
