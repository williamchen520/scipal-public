from __future__ import annotations

import unittest

from services.audit.ledger_verification import diff_ledgers, verify_ledger


class LedgerVerificationTest(unittest.TestCase):
    def _ledger(self):
        return {
            "claims": [{"claim_id": "cl_1", "text": "x", "cited_sentence_ids": ["s1"]}],
            "evidence": [{"sentence_id": "s1", "paper_id": "p1"}],
        }

    def test_ok(self):
        self.assertTrue(verify_ledger(self._ledger())["ok"])

    def test_uncited(self):
        ledger = self._ledger()
        ledger["claims"][0]["cited_sentence_ids"] = []
        self.assertFalse(verify_ledger(ledger)["ok"])

    def test_diff(self):
        old = self._ledger()
        new = self._ledger()
        new["claims"][0]["text"] = "y"
        self.assertIn("changed", diff_ledgers(old, new))


if __name__ == "__main__":
    unittest.main()
