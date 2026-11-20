"""A3 annotation tests."""

from __future__ import annotations

import os
import unittest
import uuid

import psycopg

from services.papers import annotations


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


class AnnotationUnitTests(unittest.TestCase):
    def test_clean_tags(self) -> None:
        self.assertEqual(annotations._clean_tags(["x", "x", " y "]), ["x", "y"])

    def test_clean_tags_rejects_non_list(self) -> None:
        with self.assertRaises(annotations.AnnotationError):
            annotations._clean_tags("x")

    def test_validate_rejects_bad_kind_color(self) -> None:
        with self.assertRaises(annotations.AnnotationError):
            annotations._validate_fields(
                kind="bad", color="yellow", comment="", tags=[]
            )
        with self.assertRaises(annotations.AnnotationError):
            annotations._validate_fields(
                kind="note", color="bad", comment="", tags=[]
            )


@unittest.skipUnless(_dsn(), "PostgreSQL DSN not configured")
class AnnotationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dsn = _dsn()
        suffix = uuid.uuid4().hex[:10]
        self.p1 = f"paper_a3_{suffix}_1"
        self.p2 = f"paper_a3_{suffix}_2"
        self.para1 = f"{self.p1}_para_1"
        self.para2 = f"{self.p2}_para_1"
        self.sent1 = f"{self.p1}_sent_1"
        self.sent2 = f"{self.p2}_sent_1"
        with psycopg.connect(self.dsn) as conn:
            for paper_id in (self.p1, self.p2):
                conn.execute(
                    "INSERT INTO papers (paper_id,title,filename,parse_engine,total_paragraphs) "
                    "VALUES (%s,'A3 annotation test','', 'test',1)",
                    (paper_id,),
                )
                para = self.para1 if paper_id == self.p1 else self.para2
                sent = self.sent1 if paper_id == self.p1 else self.sent2
                conn.execute(
                    "INSERT INTO paragraphs (para_id,paper_id,text,sequence,parse_engine) "
                    "VALUES (%s,%s,'test paragraph',1,'test')",
                    (para, paper_id),
                )
                conn.execute(
                    "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence) "
                    "VALUES (%s,%s,%s,'test sentence',1)",
                    (sent, para, paper_id),
                )
            conn.commit()

    def tearDown(self) -> None:
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "DELETE FROM paper_annotations WHERE paper_id IN (%s,%s)",
                (self.p1, self.p2),
            )
            conn.execute(
                "DELETE FROM sentences WHERE paper_id IN (%s,%s)", (self.p1, self.p2)
            )
            conn.execute(
                "DELETE FROM paragraphs WHERE paper_id IN (%s,%s)", (self.p1, self.p2)
            )
            conn.execute(
                "DELETE FROM papers WHERE paper_id IN (%s,%s)", (self.p1, self.p2)
            )
            conn.commit()

    def test_sentence_and_paragraph_and_note(self) -> None:
        sentence = annotations.create_annotation(
            paper_id=self.p1,
            sentence_id=self.sent1,
            comment="sentence",
            dsn=self.dsn,
        )
        self.assertEqual(sentence["sentence_id"], self.sent1)
        paragraph = annotations.create_annotation(
            paper_id=self.p1, para_id=self.para1, comment="paragraph", dsn=self.dsn
        )
        self.assertEqual(paragraph["para_id"], self.para1)
        note = annotations.create_annotation(
            paper_id=self.p1, kind="note", comment="paper note", dsn=self.dsn
        )
        self.assertEqual(note["kind"], "note")
        self.assertEqual(len(annotations.list_annotations(self.p1, dsn=self.dsn)), 3)

    def test_cross_paper_target_rejected(self) -> None:
        with self.assertRaises(annotations.AnnotationConflict):
            annotations.create_annotation(
                paper_id=self.p1, sentence_id=self.sent2, dsn=self.dsn
            )

    def test_soft_delete_and_tag_filter(self) -> None:
        row = annotations.create_annotation(
            paper_id=self.p1, sentence_id=self.sent1, tags=["a3", "keep"], dsn=self.dsn
        )
        self.assertEqual(
            len(annotations.list_annotations(self.p1, tag="a3", dsn=self.dsn)), 1
        )
        annotations.delete_annotation(row["annotation_id"], paper_id=self.p1, dsn=self.dsn)
        self.assertEqual(
            len(annotations.list_annotations(self.p1, tag="a3", dsn=self.dsn)), 0
        )
        with self.assertRaises(annotations.AnnotationNotFound):
            annotations.delete_annotation(
                row["annotation_id"], paper_id=self.p1, dsn=self.dsn
            )

    def test_update_is_paper_scoped(self) -> None:
        row = annotations.create_annotation(
            paper_id=self.p1, sentence_id=self.sent1, dsn=self.dsn
        )
        with self.assertRaises(annotations.AnnotationNotFound):
            annotations.update_annotation(
                row["annotation_id"], paper_id=self.p2, comment="x", dsn=self.dsn
            )

    def test_canonical_counts_unchanged(self) -> None:
        with psycopg.connect(self.dsn) as conn:
            before = conn.execute(
                "SELECT count(*) FROM paragraphs WHERE paper_id=%s", (self.p1,)
            ).fetchone()[0]
        annotations.create_annotation(
            paper_id=self.p1, sentence_id=self.sent1, comment="no canonical write", dsn=self.dsn
        )
        with psycopg.connect(self.dsn) as conn:
            after = conn.execute(
                "SELECT count(*) FROM paragraphs WHERE paper_id=%s", (self.p1,)
            ).fetchone()[0]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
