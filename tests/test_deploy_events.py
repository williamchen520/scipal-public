from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.deploy_events import read_events, record, rollback_metrics


class DeployEventsTest(unittest.TestCase):
    def test_rollback_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            record(env="staging", action="deploy", version="v1", path=path,
                   timestamp="2026-01-01T00:00:00+00:00")
            record(env="staging", action="rollback", version="v0", path=path,
                   timestamp="2026-01-01T02:00:00+00:00")
            result = rollback_metrics(read_events(path))
            self.assertEqual(result["deployments"], 1)
            self.assertEqual(result["rollbacks"], 1)
            self.assertEqual(result["median_rollback_hours"], 2.0)

    def test_no_events_is_null(self):
        result = rollback_metrics([])
        self.assertIsNone(result["median_rollback_hours"])
        self.assertEqual(result["deployments"], 0)


if __name__ == "__main__":
    unittest.main()
