from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from services.audit import event_chain


class EventChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("SCIPAL_EVENT_CHAIN_PATH")
        os.environ["SCIPAL_EVENT_CHAIN_PATH"] = str(Path(self.tmp.name) / "chain.jsonl")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("SCIPAL_EVENT_CHAIN_PATH", None)
        else:
            os.environ["SCIPAL_EVENT_CHAIN_PATH"] = self.old
        self.tmp.cleanup()

    def test_append_verify(self):
        event_chain.append("a1", "action", {"action": "accept"})
        event_chain.append("a1", "revision", {"revision": 2})
        self.assertTrue(event_chain.verify("a1")["ok"])
        self.assertEqual(event_chain.verify("a1")["events"], 2)

    def test_tamper(self):
        event_chain.append("a1", "action", {"action": "accept"})
        path = Path(os.environ["SCIPAL_EVENT_CHAIN_PATH"])
        row = json.loads(path.read_text(encoding="utf-8").strip())
        row["payload"]["action"] = "reject"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        self.assertFalse(event_chain.verify("a1")["ok"])
