from __future__ import annotations

import unittest

from code_rag.executions import summarize_executions


class ExecutionStatsTest(unittest.TestCase):
    def test_summary(self):
        result = summarize_executions([
            {"status": "passed", "duration_seconds": 1.0},
            {"status": "passed", "duration_seconds": 3.0},
            {"status": "failed", "duration_seconds": 2.0},
            {"status": "timeout", "duration_seconds": None},
        ])
        self.assertEqual(result["executions"], 4)
        self.assertEqual(result["passed"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["timeouts"], 1)
        self.assertEqual(result["pass_rate"], 0.5)
        self.assertEqual(result["median_duration_seconds"], 2.0)


if __name__ == "__main__":
    unittest.main()
