"""S1 v1.1 corrected-label integrity tests."""

from __future__ import annotations

import json
import os
import unittest
from collections import Counter
from pathlib import Path

import psycopg

QUESTIONS = Path(__file__).resolve().parent.parent / "eval" / "s1_internal_questions.v1.1.jsonl"


def _rows() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line]


def _dsn() -> str:
    return os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()


class V11QuestionTests(unittest.TestCase):
    def test_count_version_categories(self) -> None:
        rows = _rows()
        self.assertEqual(len(rows), 50)
        self.assertTrue(all(row.get("version") == "1.1" for row in rows))
        self.assertEqual(
            Counter(row["category"] for row in rows),
            Counter({"factoid": 20, "method": 10, "dataset": 10, "comparison": 5, "contradiction": 5}),
        )

    def test_corrected_questions(self) -> None:
        rows = {row["question_id"]: row for row in _rows()}
        self.assertIn("In which cases", rows["s1-016"]["question"])
        self.assertIn("In the heart", rows["s1-021"]["question"])
        self.assertIn("Elektra and Alien", rows["s1-025"]["question"])
        self.assertEqual(len(rows["s1-046"]["acceptable_sentence_ids"]), 3)

    @unittest.skipUnless(_dsn(), "PostgreSQL DSN not configured")
    def test_acceptable_ids_exist(self) -> None:
        with psycopg.connect(_dsn()) as conn:
            for row in _rows():
                for sentence_id in row.get("acceptable_sentence_ids") or []:
                    found = conn.execute(
                        "SELECT 1 FROM sentences WHERE sentence_id=%s", (sentence_id,)
                    ).fetchone()
                    self.assertIsNotNone(found, sentence_id)


if __name__ == "__main__":
    unittest.main()
