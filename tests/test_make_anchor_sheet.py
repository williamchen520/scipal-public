from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.make_anchor_sheet import make_sheet


class MakeAnchorSheetTest(unittest.TestCase):
    def test_blind_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            questions = root / "q.jsonl"
            questions.write_text('{"question_id":"q1","question":"What induces TAK1?","gold_sentence_ids":["s1"]}\n', encoding="utf-8")
            out = root / "sheet.csv"
            self.assertEqual(make_sheet(questions, out), 1)
            rows = list(csv.DictReader(out.open(encoding="utf-8", newline="")))
            self.assertEqual(rows[0]["question_id"], "q1")
            self.assertNotIn("baseline_ndcg", rows[0])
            with self.assertRaises(FileExistsError):
                make_sheet(questions, out)


if __name__ == "__main__":
    unittest.main()
