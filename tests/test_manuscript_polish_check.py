from __future__ import annotations

import unittest

from scripts.manuscript_polish_check import check


class ManuscriptPolishCheckTest(unittest.TestCase):
    def test_unchanged(self):
        text = "Treatment was associated with response in 12 patients [1]."
        result = check(text, text)
        self.assertTrue(result["ok"])

    def test_citation_change(self):
        result = check("Response [1].", "Response [2].")
        self.assertFalse(result["ok"])
        self.assertIn("citations changed or reordered", result["issues"])

    def test_number_change(self):
        result = check("12 patients [1].", "13 patients [1].")
        self.assertFalse(result["ok"])
        self.assertIn("numbers/units changed", result["issues"])

    def test_hedge_removed(self):
        result = check("Treatment may improve response [1].", "Treatment improves response [1].")
        self.assertFalse(result["ok"])
        self.assertIn("hedges removed", result["issues"])

    def test_causal_strengthening(self):
        result = check("Treatment was associated with response [1].", "Treatment causes response [1].")
        self.assertFalse(result["ok"])
        self.assertIn("causal language strengthened", result["issues"])


if __name__ == "__main__":
    unittest.main()
