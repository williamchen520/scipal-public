from __future__ import annotations

import unittest

from services.audit.evidence_ledger import build_ledger, claims_from_claim_audit, validate_ledger
from services.audit.ledger_contract import text_hash, validate_contract


class EvidenceLedgerTest(unittest.TestCase):
    def _evidence(self):
        return [
            {"sentence_id": "s1", "paper_id": "p1", "text": "cited", "rerank_score": 0.9},
            {"sentence_id": "s2", "paper_id": "p1", "text": "uncited high", "rerank_score": 0.95},
            {"sentence_id": "s3", "paper_id": "p2", "text": "cited low", "rerank_score": 0.1},
        ]

    def test_priority_and_claims(self):
        ledger = build_ledger(
            query="q", answer="a", evidence=self._evidence(),
            claims=[{"text": "claim", "cited_sentence_ids": ["s1", "s3"]}],
        )
        self.assertEqual(validate_ledger(ledger), [])
        priorities = {ref["sentence_id"]: ref["review_priority"] for ref in ledger["evidence"]}
        self.assertEqual(priorities["s2"], "high")
        self.assertEqual(priorities["s3"], "high")
        self.assertEqual(ledger["claims"][0]["support_status"], "cited")
        self.assertEqual(ledger["summary"]["cited_evidence"], 2)

    def test_unknown_evidence(self):
        ledger = build_ledger(
            query="q", answer="a", evidence=self._evidence(),
            claims=[{"text": "claim", "cited_sentence_ids": ["missing"]}],
        )
        self.assertEqual(ledger["claims"][0]["support_status"], "unknown_evidence")
        self.assertEqual(ledger["claims"][0]["unknown_sentence_ids"], ["missing"])

    def test_snapshot_and_scope(self):
        ledger = build_ledger(
            query="q", answer="a", evidence=self._evidence(),
            corpus_snapshot_id="snap1", scope={"paper_ids": ["p1"]},
        )
        self.assertEqual(ledger["corpus_snapshot_id"], "snap1")
        self.assertEqual(ledger["scope"]["paper_ids"], ["p1"])


if __name__ == "__main__":
    unittest.main()


class ClaimAuditMapTest(unittest.TestCase):
    def test_marker_to_sentence(self):
        evidence = [{"sentence_id": "s1"}, {"sentence_id": "s2"}]
        claims = claims_from_claim_audit({"claims": [{"claim": "c", "citations": ["[P2]"]}]}, evidence)
        self.assertEqual(claims[0]["cited_sentence_ids"], ["s2"])


class LedgerContractTest(unittest.TestCase):
    def test_contract(self):
        ledger = build_ledger(
            query="q", answer="a", evidence=[
                {"sentence_id": "s1", "paper_id": "p1", "text": "evidence", "rerank_score": 0.8},
            ],
            claims=[{"text": "claim", "cited_sentence_ids": ["s1"]}],
            corpus_snapshot_id="snap1",
        )
        self.assertEqual(validate_contract(ledger), [])
        self.assertEqual(ledger["answer_text_hash"], text_hash("a"))
        self.assertEqual(ledger["chain_id"], ledger["answer_id"])
        self.assertEqual(ledger["claims"][0]["unit_role"], "answer_claim")
        self.assertEqual(ledger["evidence"][0]["unit_role"], "evidence")
