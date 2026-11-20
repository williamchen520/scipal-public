from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.audit_queue import build_audit_queue_blueprint
from services.audit import queue


class AuditQueueApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("SCIPAL_AUDIT_QUEUE_PATH")
        self.old_state = os.environ.get("SCIPAL_AUDIT_QUEUE_STATE_PATH")
        os.environ["SCIPAL_AUDIT_QUEUE_PATH"] = str(Path(self.tmp.name) / "q.jsonl")
        os.environ["SCIPAL_AUDIT_QUEUE_STATE_PATH"] = str(Path(self.tmp.name) / "s.jsonl")
        self.event = queue.enqueue(audit={"query": "q", "coverage": {"facet_status": "partial", "provenance_complete": True}})
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_audit_queue_blueprint())
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        for key, old in (("SCIPAL_AUDIT_QUEUE_PATH", self.old), ("SCIPAL_AUDIT_QUEUE_STATE_PATH", self.old_state)):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        self.tmp.cleanup()

    def _login(self):
        with self.client.session_transaction() as session:
            session["user_id"] = "u"

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/audit/queue").status_code, 401)

    def test_list_and_mark(self):
        self._login()
        self.assertEqual(self.client.get("/api/audit/queue").status_code, 200)
        response = self.client.post(f"/api/audit/queue/{self.event['queue_id']}", json={"status": "reviewed"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "reviewed")


if __name__ == "__main__":
    unittest.main()
