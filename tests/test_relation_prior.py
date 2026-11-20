from __future__ import annotations

import unittest

from scripts.relation_prior import apply_relation_prior


class RelationPriorTest(unittest.TestCase):
    def test_lambda_zero_keeps_base_order(self):
        rows = apply_relation_prior(
            {"a": 0.9, "b": 0.8},
            {"a": 0.0, "b": 1.0},
            lam=0.0,
            citation_count={"a": 10, "b": 10},
            age_days={"a": 1000, "b": 1000},
        )
        self.assertEqual([row["paper_id"] for row in rows], ["a", "b"])
        self.assertEqual(rows[0]["boost"], 0.0)

    def test_no_citations_disables_prior(self):
        rows = apply_relation_prior(
            {"a": 0.5, "b": 0.5},
            {"a": 0.0, "b": 1.0},
            citation_count={"a": 0, "b": 0},
            age_days={"a": 1000, "b": 1000},
        )
        self.assertEqual({row["paper_id"]: row["boost"] for row in rows}, {"a": 0.0, "b": 0.0})

    def test_recent_paper_disables_prior(self):
        rows = apply_relation_prior(
            {"a": 0.5, "b": 0.5},
            {"a": 0.0, "b": 1.0},
            citation_count={"a": 10, "b": 10},
            age_days={"a": 1000, "b": 10},
        )
        by_id = {row["paper_id"]: row for row in rows}
        self.assertEqual(by_id["b"]["gate"]["recency"], 0.0)
        self.assertEqual(by_id["b"]["boost"], 0.0)

    def test_old_cited_can_reorder_with_cap(self):
        rows = apply_relation_prior(
            {"a": 0.5, "b": 0.5},
            {"a": 0.0, "b": 1.0},
            lam=1.0,
            max_boost=0.1,
            citation_count={"a": 10, "b": 10},
            age_days={"a": 1000, "b": 1000},
        )
        self.assertEqual(rows[0]["paper_id"], "b")
        self.assertLessEqual(rows[0]["boost"], 0.1)


if __name__ == "__main__":
    unittest.main()
