from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from services.audit import queue


class AuditQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("SCIPAL_AUDIT_QUEUE_PATH")
        self.old_state = os.environ.get("SCIPAL_AUDIT_QUEUE_STATE_PATH")
        os.environ["SCIPAL_AUDIT_QUEUE_PATH"] = str(Path(self.tmp.name) / "q.jsonl")
        os.environ["SCIPAL_AUDIT_QUEUE_STATE_PATH"] = str(Path(self.tmp.name) / "state.jsonl")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("SCIPAL_AUDIT_QUEUE_PATH", None)
        else:
            os.environ["SCIPAL_AUDIT_QUEUE_PATH"] = self.old
        if self.old_state is None:
            os.environ.pop("SCIPAL_AUDIT_QUEUE_STATE_PATH", None)
        else:
            os.environ["SCIPAL_AUDIT_QUEUE_STATE_PATH"] = self.old_state
        self.tmp.cleanup()

    def test_clean_audit_not_queued(self):
        event = queue.enqueue(audit={"coverage": {"status": "covered", "facet_status": "covered", "provenance_complete": True}})
        self.assertIsNone(event)

    def test_facet_partial_queued(self):
        event = queue.enqueue(audit={"audit_id": "a", "query": "q", "coverage": {"facet_status": "partial", "provenance_complete": True}})
        self.assertIn("facet_partial", event["reasons"])
        self.assertEqual(queue.list_events()[-1]["queue_id"], event["queue_id"])

    def test_verification_failed_queued(self):
        event = queue.enqueue(
            audit={"query": "q", "coverage": {}},
            claim_audit={"status": "covered", "claims_total": 1, "verification_ok": False},
            source="qa",
        )
        self.assertIn("verification_failed", event["reasons"])


if __name__ == "__main__":
    unittest.main()


class AuditQueueMarkTest(unittest.TestCase):
    def test_mark_reviewed(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("SCIPAL_AUDIT_QUEUE_PATH")
            old_state = os.environ.get("SCIPAL_AUDIT_QUEUE_STATE_PATH")
            os.environ["SCIPAL_AUDIT_QUEUE_PATH"] = str(Path(tmp) / "q.jsonl")
            os.environ["SCIPAL_AUDIT_QUEUE_STATE_PATH"] = str(Path(tmp) / "state.jsonl")
            try:
                event = queue.enqueue(audit={"query": "q", "coverage": {"facet_status": "partial", "provenance_complete": True}})
                self.assertEqual(queue.list_events()[-1]["status"], "open")
                marked = queue.mark(event["queue_id"], "reviewed", "ok")
                self.assertEqual(marked["status"], "reviewed")
                self.assertEqual(queue.list_events()[-1]["status"], "reviewed")
            finally:
                for key, old_value in (("SCIPAL_AUDIT_QUEUE_PATH", old), ("SCIPAL_AUDIT_QUEUE_STATE_PATH", old_state)):
                    if old_value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old_value
