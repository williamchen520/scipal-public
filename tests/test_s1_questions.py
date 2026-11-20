"""S1.1 internal question set integrity tests."""

from __future__ import annotations

import json
import os
import unittest
from collections import Counter
from pathlib import Path

import psycopg

QUESTIONS = Path(__file__).resolve().parent.parent / "eval" / "s1_internal_questions.jsonl"


def _rows() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line]


def _dsn() -> str:
    return os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()


class QuestionSetTests(unittest.TestCase):
    def test_count_and_categories(self) -> None:
        rows = _rows()
        self.assertEqual(len(rows), 50)
        self.assertEqual(
            Counter(row["category"] for row in rows),
            Counter(
                {
                    "factoid": 20,
                    "method": 10,
                    "dataset": 10,
                    "comparison": 5,
                    "contradiction": 5,
                }
            ),
        )
        self.assertEqual(len({row["question_id"] for row in rows}), 50)

    @unittest.skipUnless(_dsn(), "PostgreSQL DSN not configured")
    def test_gold_sentences_exist_and_belong(self) -> None:
        with psycopg.connect(_dsn()) as conn:
            for row in _rows():
                for sentence_id in row["gold_sentence_ids"]:
                    found = conn.execute(
                        "SELECT paper_id FROM sentences WHERE sentence_id=%s",
                        (sentence_id,),
                    ).fetchone()
                    self.assertIsNotNone(found, sentence_id)
                    self.assertEqual(found[0], row["gold_paper_id"], sentence_id)


if __name__ == "__main__":
    unittest.main()
