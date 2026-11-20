from __future__ import annotations

import unittest
from pathlib import Path


class ReviewCitationUiTest(unittest.TestCase):
    def test_review_has_verify_entry(self):
        html = Path("frontend/reviews.html").read_text(encoding="utf-8")
        self.assertIn('id="verify-refs-btn"', html)
        self.assertIn("/api/citation-integrity/check-batch", html)
        self.assertIn("data-ref-check", html)


if __name__ == "__main__":
    unittest.main()
