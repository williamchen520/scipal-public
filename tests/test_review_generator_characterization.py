"""Characterization tests for ReviewGenerator pure helpers.

These tests do not construct the LLM client or touch a database.
"""

from __future__ import annotations

import unittest

from services.review.models import EvidenceCard, ReviewSentence
from services.review.review_generator import ReviewGenerator, assign_papers_to_outline


def card(eid: str, paper_id: str = "p1", content: str = "STAT1 phosphorylation increased",
         confidence: float = 1.0) -> EvidenceCard:
    return EvidenceCard(
        evidence_id=eid,
        paper_id=paper_id,
        para_id=f"a_{eid}",
        content=content,
        confidence=confidence,
    )


def generator(**attrs) -> ReviewGenerator:
    obj = object.__new__(ReviewGenerator)
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


class ReviewGeneratorCharacterizationTests(unittest.TestCase):
    def test_extract_2grams(self):
        self.assertEqual(ReviewGenerator._extract_2grams("STAT1!"), {"st", "ta", "at", "t1"})
        self.assertEqual(ReviewGenerator._extract_2grams(""), set())

    def test_format_ref_numbers(self):
        self.assertEqual(ReviewGenerator._format_ref_numbers([1, 2, 3]), "[1-3]")
        self.assertEqual(ReviewGenerator._format_ref_numbers([1, 3, 5]), "[1,3,5]")
        self.assertEqual(ReviewGenerator._format_ref_numbers([3, 1, 2]), "[1-3]")

    def test_remap_keeps_source_ids(self):
        cards = [card("long-a"), card("long-b")]
        ReviewGenerator._remap_to_short_ids(cards)
        self.assertEqual([c.evidence_id for c in cards], ["ev_001", "ev_002"])
        self.assertEqual([c.para_id for c in cards], ["a_long-a", "a_long-b"])

    def test_limit_evidence_per_paper(self):
        gen = generator(max_evidence_per_paper=2)
        cards = [
            card("a1", "p1", confidence=0.5),
            card("a2", "p1", confidence=0.9),
            card("a3", "p1", confidence=0.8),
            card("b1", "p2", confidence=0.1),
        ]
        kept = gen._limit_evidence_per_paper(cards)
        self.assertEqual({c.evidence_id for c in kept}, {"a2", "a3", "b1"})

    def test_split_and_link_filters_unknown_ids(self):
        gen = generator()
        text = "STAT1 increased [ev_001]. Other claim [ev_999]."
        sentences = gen._split_and_link(text, "s1", [card("ev_001")], 0)
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0].evidence_ids, ["ev_001"])
        self.assertEqual(sentences[1].evidence_ids, [])
        self.assertNotIn("[ev_", sentences[0].text)

    def test_auto_cite_uses_overlap(self):
        gen = generator()
        sentence = ReviewSentence(
            sentence_id="sent_s1_0",
            section_id="s1",
            text="STAT1 phosphorylation increased",
        )
        count = gen._auto_cite_sentences([sentence], [card("ev_001")])
        self.assertEqual(count, 1)
        self.assertEqual(sentence.evidence_ids, ["ev_001"])
        self.assertIn("自动补引用", sentence.verification_note)

    def test_assign_papers_to_outline(self):
        outline = {
            "sections": [
                {
                    "section_id": "s1",
                    "title": "STAT1 signaling",
                    "description": "",
                    "paragraphs": [{"topic": "STAT1", "description": ""}],
                }
            ]
        }
        papers = [{"paper_id": "p1", "title": "STAT1 signaling"}]
        result = assign_papers_to_outline(outline, papers)
        self.assertEqual(result["sections"][0]["assigned_paper_ids"], ["p1"])
        self.assertEqual(result["sections"][0]["paragraphs"][0]["assigned_paper_ids"], ["p1"])


if __name__ == "__main__":
    unittest.main()
