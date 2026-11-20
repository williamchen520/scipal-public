from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from services.audit.error_lifecycle import create, get, list_errors, transition


class ErrorLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("SCIPAL_ERRORS_PATH")
        os.environ["SCIPAL_ERRORS_PATH"] = str(Path(self.tmp.name) / "errors.jsonl")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("SCIPAL_ERRORS_PATH", None)
        else:
            os.environ["SCIPAL_ERRORS_PATH"] = self.old
        self.tmp.cleanup()

    def test_lifecycle(self):
        event = create(answer_id="a1", error_type="remove_claim", target_id="cl_1")
        error_id = event["error_id"]
        self.assertEqual(get(error_id)["status"], "detected")
        transition(error_id, "triaged")
        transition(error_id, "repair_proposed")
        transition(error_id, "repaired")
        transition(error_id, "verified")
        transition(
            error_id,
            "closed",
            revision_answer_id="ans_new",
            verification_ok=True,
            diff="claim removed",
        )
        self.assertEqual(get(error_id)["status"], "closed")
        self.assertEqual(len(list_errors()), 1)

    def test_invalid_transition(self):
        event = create(answer_id="a1", error_type="x", target_id="t")
        with self.assertRaises(ValueError):
            transition(event["error_id"], "closed")

    def test_close_requires_bindings(self):
        event = create(answer_id="a1", error_type="x", target_id="t")
        error_id = event["error_id"]
        transition(error_id, "triaged")
        transition(error_id, "repair_proposed")
        transition(error_id, "repaired")
        transition(error_id, "verified")
        with self.assertRaises(ValueError):
            transition(error_id, "closed")
