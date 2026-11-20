from __future__ import annotations

import unittest

from services.audit.claim_audit import build_claim_audit


class ClaimAuditTest(unittest.TestCase):
    def test_partial_citation(self):
        answer = (
            "The treatment significantly improves progression free survival in this cohort [P1]. "
            "The mechanism remains uncertain and requires further validation in independent models."
        )
        audit = build_claim_audit(
            answer=answer,
            verification={"ok": False, "missing_ids": ["[P2]"]},
            grounding={"grounded": True},
        )
        self.assertEqual(audit["claims_total"], 2)
        self.assertEqual(audit["claims_cited"], 1)
        self.assertEqual(audit["status"], "partial")
        self.assertEqual(audit["citation_coverage"], 0.5)
        self.assertEqual(audit["unknown_citations"], ["[P2]"])
        self.assertFalse(audit["verification_ok"])

    def test_no_claims(self):
        audit = build_claim_audit(answer="Short.", verification={})
        self.assertEqual(audit["status"], "not_computed")
        self.assertIsNone(audit["citation_coverage"])


if __name__ == "__main__":
    unittest.main()
