from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from services.audit.review_actions import list_actions, record


class ReviewActionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("SCIPAL_LEDGER_ACTIONS_PATH")
        os.environ["SCIPAL_LEDGER_ACTIONS_PATH"] = str(Path(self.tmp.name) / "actions.jsonl")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("SCIPAL_LEDGER_ACTIONS_PATH", None)
        else:
            os.environ["SCIPAL_LEDGER_ACTIONS_PATH"] = self.old
        self.tmp.cleanup()

    def test_record_and_list(self):
        event = record(answer_id="a1", action="accept", target_id="cl_1", actor="u")
        self.assertEqual(event["action"], "accept")
        self.assertEqual(list_actions("a1")[0]["target_id"], "cl_1")

    def test_invalid_action(self):
        with self.assertRaises(ValueError):
            record(answer_id="a1", action="delete")
