from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from services.audit.metrics import metrics


class AuditMetricsTest(unittest.TestCase):
    def test_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = {key: os.environ.get(key) for key in ("SCIPAL_LEDGER_PATH", "SCIPAL_ERRORS_PATH", "SCIPAL_LEDGER_ACTIONS_PATH")}
            os.environ["SCIPAL_LEDGER_PATH"] = str(root / "ledgers.jsonl")
            os.environ["SCIPAL_ERRORS_PATH"] = str(root / "errors.jsonl")
            os.environ["SCIPAL_LEDGER_ACTIONS_PATH"] = str(root / "actions.jsonl")
            try:
                (root / "ledgers.jsonl").write_text(json.dumps({
                    "claims": [{"support_status": "cited"}],
                    "evidence": [{"cited": True, "review_priority": "high"}],
                }) + "\n", encoding="utf-8")
                (root / "errors.jsonl").write_text(json.dumps({"error_id": "e1", "status": "closed"}) + "\n", encoding="utf-8")
                (root / "actions.jsonl").write_text(json.dumps({"action": "accept"}) + "\n", encoding="utf-8")
                result = metrics()
                self.assertEqual(result["ledgers"], 1)
                self.assertEqual(result["errors_by_status"], {"closed": 1})
                self.assertEqual(result["closure_rate"], 1.0)
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
