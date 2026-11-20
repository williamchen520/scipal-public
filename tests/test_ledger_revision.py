from __future__ import annotations

import unittest

from services.audit.ledger_revision import revise


def _ledger():
    return {
        "answer_id": "a1",
        "query": "q",
        "claims": [{"claim_id": "cl_1", "cited_sentence_ids": ["s1"], "known_sentence_ids": ["s1"], "unknown_sentence_ids": [], "support_status": "cited"}],
        "evidence": [{"sentence_id": "s1", "paper_id": "p1", "rerank_score": 0.9, "cited": True, "review_priority": "low"}],
        "summary": {},
    }


class LedgerRevisionTest(unittest.TestCase):
    def test_remove_claim_keeps_original(self):
        old = _ledger()
        new = revise(old, action="remove_claim", target_id="cl_1")
        self.assertEqual(len(old["claims"]), 1)
        self.assertEqual(new["claims"], [])
        self.assertEqual(new["parent_answer_id"], "a1")
        self.assertNotEqual(new["answer_id"], "a1")

    def test_add_evidence(self):
        new = revise(
            _ledger(), action="add_evidence", target_id="cl_1",
            evidence={"sentence_id": "s2", "paper_id": "p2", "rerank_score": 0.8},
        )
        self.assertEqual([item["sentence_id"] for item in new["evidence"]], ["s1", "s2"])
        self.assertIn("s2", new["claims"][0]["cited_sentence_ids"])

    def test_rewrite_claim(self):
        new = revise(
            _ledger(), action="rewrite_claim", target_id="cl_1",
            new_text="rewritten [P1]", evidence_ids=["s1"],
        )
        self.assertEqual(new["claims"][0]["text"], "rewritten [P1]")
        self.assertEqual(new["claims"][0]["cited_sentence_ids"], ["s1"])

    def test_rewrite_out_of_scope_rejected(self):
        with self.assertRaises(ValueError):
            revise(
                _ledger(), action="rewrite_claim", target_id="cl_1",
                new_text="outside [P2]", evidence_ids=["s1"],
            )

    def test_flag_missing(self):
        new = revise(_ledger(), action="flag_missing", target_id="cl_1", note="missing")
        self.assertEqual(new["unresolved"][0]["target_id"], "cl_1")

    def test_invalid_action(self):
        with self.assertRaises(ValueError):
            revise(_ledger(), action="accept", target_id="cl_1")
