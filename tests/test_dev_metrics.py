from __future__ import annotations

import unittest

from scripts.dev_metrics import percentile, summarize_prs


class DevMetricsTest(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(percentile([], 90), None)
        self.assertEqual(percentile([1, 2, 3, 4], 90), 4)

    def test_summarize(self):
        prs = [
            {"additions": 10, "deletions": 5, "created_at": "2026-01-01T00:00:00Z",
             "merged_at": "2026-01-01T02:00:00Z", "labels": []},
            {"additions": 20, "deletions": 0, "created_at": "2026-01-01T00:00:00Z",
             "merged_at": "2026-01-02T00:00:00Z", "labels": [{"name": "incident"}]},
        ]
        result = summarize_prs(prs)
        self.assertEqual(result["merged_prs"], 2)
        self.assertEqual(result["median_pr_size"], 17.5)
        self.assertEqual(result["failure_prs"], 1)
        self.assertEqual(result["change_failure_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
