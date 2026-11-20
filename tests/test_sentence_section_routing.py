"""S2.2: section-routing query cue tests."""

from __future__ import annotations

import unittest

from services.search.sentence_hybrid import SentenceHybridRetriever


class SectionRouteTests(unittest.TestCase):
    def test_dataset(self) -> None:
        terms = SentenceHybridRetriever._route_terms(
            "Which mouse model was used to study microglia?"
        )
        self.assertIn("method", terms)

    def test_limitation(self) -> None:
        terms = SentenceHybridRetriever._route_terms(
            "What limitations does this CAR-T approach have?"
        )
        self.assertIn("discussion", terms)

    def test_no_route(self) -> None:
        self.assertEqual(
            SentenceHybridRetriever._route_terms("What is COP1?"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
