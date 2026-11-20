from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_proposal import apply_proposal


class ApplyProposalTest(unittest.TestCase):
    def test_requires_approve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = root / "p.json"
            proposal.write_text(json.dumps({"files": [{"path": "a.py", "content": "x=1\n"}]}), encoding="utf-8")
            apply_proposal(proposal, root, approve=False)
            self.assertFalse((root / "a.py").exists())
            apply_proposal(proposal, root, approve=True)
            self.assertEqual((root / "a.py").read_text(encoding="utf-8"), "x=1\n")

    def test_rejects_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal = root / "p.json"
            proposal.write_text(json.dumps({"files": [{"path": "../x.py", "content": "x=1\n"}]}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                apply_proposal(proposal, root, approve=True)


if __name__ == "__main__":
    unittest.main()
