"""S3.D: online search is opt-in by default."""

from __future__ import annotations

import unittest

from routes.search import as_bool


class OnlineFlagTests(unittest.TestCase):
    def test_missing_is_false(self) -> None:
        self.assertFalse(as_bool(None))

    def test_false_string_is_false(self) -> None:
        self.assertFalse(as_bool("false"))
        self.assertFalse(as_bool("0"))

    def test_true_strings(self) -> None:
        self.assertTrue(as_bool("true"))
        self.assertTrue(as_bool("1"))
        self.assertTrue(as_bool(True))


if __name__ == "__main__":
    unittest.main()
