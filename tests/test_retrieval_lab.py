from __future__ import annotations

import unittest

from scripts.retrieval_lab import parity, replay


def trace(final_ids, top_k=2):
    return {
        "trace_id": "t1",
        "config": {"top_k": top_k},
        "pool": [
            {"sentence_id": "s1", "rerank_score": 0.2},
            {"sentence_id": "s2", "rerank_score": 0.9},
            {"sentence_id": "s3", "rerank_score": 0.5},
        ],
        "final": [{"sentence_id": item} for item in final_ids],
    }


class RetrievalLabTest(unittest.TestCase):
    def test_replay_baseline(self):
        self.assertEqual(replay(trace(["s2", "s3"])), ["s2", "s3"])

    def test_parity_ok(self):
        self.assertTrue(parity(trace(["s2", "s3"]))["ok"])

    def test_parity_mismatch(self):
        self.assertFalse(parity(trace(["s3", "s2"]))["ok"])


if __name__ == "__main__":
    unittest.main()


class AlignmentTest(unittest.TestCase):
    def test_unaligned_gold_is_explicit(self):
        from scripts.retrieval_lab import evaluate
        row = trace(["s2", "s3"])
        result = evaluate([row], {"q": {"para_other_sent_1"}}, lam=0.0, mu=0.0)
        self.assertFalse(result["aligned"])
