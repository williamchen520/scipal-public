"""S3.C: default retrieval configuration guard tests."""

from __future__ import annotations

import unittest

from scripts.check_retrieval_defaults import check_defaults


class RetrievalDefaultsTests(unittest.TestCase):
    def test_sentence_default_ok(self) -> None:
        result = check_defaults({})
        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence_backend"], "sentence")
        self.assertEqual(result["experimental_enabled"], {})

    def test_experimental_flag_fails(self) -> None:
        result = check_defaults({"SCIPAL_SENTENCE_EXPANSION": "1"})
        self.assertFalse(result["ok"])
        self.assertIn("SCIPAL_SENTENCE_EXPANSION", result["experimental_enabled"])

    def test_unified_fails_default(self) -> None:
        result = check_defaults({"SCIPAL_EVIDENCE_BACKEND": "unified"})
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
