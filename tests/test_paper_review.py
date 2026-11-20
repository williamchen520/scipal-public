"""N1 review gate tests."""

from __future__ import annotations

import unittest

from services.papers.review import ReviewError, quality_summary, set_decision


class ReviewTests(unittest.TestCase):
    def test_quality_good(self) -> None:
        result = quality_summary(
            title="A valid paper title",
            abstract="A" * 150,
            paragraphs=10,
            sections=4,
            sentences=40,
            code_links=1,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["metrics"]["validated_code_links"], 1)

    def test_quality_bad(self) -> None:
        result = quality_summary(
            title="x", abstract="", paragraphs=1, sections=0, sentences=1, code_links=0
        )
        self.assertFalse(result["ok"])
        self.assertIn("title too short", result["issues"])

    def test_invalid_decision(self) -> None:
        with self.assertRaises(ReviewError):
            set_decision("paper_x", "maybe")


if __name__ == "__main__":
    unittest.main()
