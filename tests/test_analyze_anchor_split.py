from __future__ import annotations

import unittest

from scripts.analyze_anchor_split import summarize


class AnalyzeAnchorSplitTest(unittest.TestCase):
    def test_grouped(self):
        rows = [
            {"anchor_type": "entity", "baseline_ndcg": "0.5", "fixed_ndcg": "0.6", "delta_ndcg": "0.1"},
            {"anchor_type": "overview", "baseline_ndcg": "0.4", "fixed_ndcg": "0.4", "delta_ndcg": "0.0"},
        ]
        result = summarize(rows)
        self.assertTrue(result["ready"])
        self.assertEqual(result["groups"]["entity"]["delta_ndcg"], 0.1)

    def test_unlabeled_blocks(self):
        result = summarize([{"anchor_type": "", "baseline_ndcg": "0", "fixed_ndcg": "0", "delta_ndcg": "0"}])
        self.assertFalse(result["ready"])
        self.assertEqual(result["unlabeled"], 1)

    def test_invalid_blocks(self):
        result = summarize([{"anchor_type": "bad", "baseline_ndcg": "0", "fixed_ndcg": "0", "delta_ndcg": "0"}])
        self.assertFalse(result["ready"])
        self.assertEqual(result["invalid"], ["bad"])


if __name__ == "__main__":
    unittest.main()


class JoinLabelsTest(unittest.TestCase):
    def test_join_and_human_source(self):
        metrics = [{"question_id": "q1", "baseline_ndcg": "0.5", "fixed_ndcg": "0.6", "delta_ndcg": "0.1"}]
        labels = [{"question_id": "q1", "anchor_type": "entity", "anchor_type_source": "human"}]
        from scripts.analyze_anchor_split import join_labels
        result = summarize(join_labels(metrics, labels))
        self.assertTrue(result["ready"])
        self.assertEqual(result["sources"], {"human": 1})

    def test_blank_source_not_human(self):
        from scripts.analyze_anchor_split import join_labels
        result = summarize(join_labels(
            [{"question_id": "q1", "baseline_ndcg": "0", "fixed_ndcg": "0", "delta_ndcg": "0"}],
            [{"question_id": "q1", "anchor_type": "entity", "anchor_type_source": "ai_prelabel"}],
        ))
        self.assertEqual(result["sources"], {"ai_prelabel": 1})
