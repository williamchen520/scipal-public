"""D2 Markdown parser and format resolver tests."""

from __future__ import annotations

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from services.online.formats import choose_format, format_from_url, resolve_candidate
from services.papers.md_parser import parse_markdown


SAMPLE = """---
title: A Markdown paper
doi: 10.1234/md.1
authors: [Alice, Bob]
journal: Test Journal
---

# A Markdown paper

## Abstract

This is the abstract. It is long enough for a paper payload. AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

## Introduction

First paragraph. BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB

Second paragraph with citation [1]. CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC

## Results

Result paragraph. DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD

## Discussion

Discussion paragraph one. EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE

Discussion paragraph two. FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
"""


class MarkdownParserTests(unittest.TestCase):
    def test_front_matter_sections_abstract(self) -> None:
        data = parse_markdown(SAMPLE.encode(), source_uri="paper.md")
        self.assertEqual(data["title"], "A Markdown paper")
        self.assertEqual(data["doi"], "10.1234/md.1")
        self.assertEqual(data["authors"], ["Alice", "Bob"])
        self.assertEqual([section["title"] for section in data["sections"]], ["Abstract", "Introduction", "Results", "Discussion"])
        self.assertIn("abstract", data["abstract"])

    def test_paper_lane_parses_md(self) -> None:
        from services.imports.paper_lane import PaperLaneAdapter

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.md"
            path.write_text(SAMPLE, encoding="utf-8")
            with mock.patch(
                "services.imports.paper_lane.session.set_item_parsed"
            ):
                status = PaperLaneAdapter(build=False).process(
                    {
                        "import_id": "imp_md",
                        "item_id": "item_1",
                        "source_kind": "md",
                        "staged_path": str(path),
                    }
                )
        self.assertEqual(status, "parsed")


class FormatTests(unittest.TestCase):
    def test_url_inference_and_priority(self) -> None:
        self.assertEqual(format_from_url("https://x/a.xml"), "jats")
        self.assertEqual(format_from_url("https://x/a.md"), "md")
        self.assertEqual(format_from_url("https://x/a", "text/html"), "html")
        self.assertEqual(choose_format(available=["pdf", "md", "html"]), "html")
        self.assertEqual(choose_format(best_format="pdf", url="https://x/a.html"), "html")

    def test_resolve_candidate(self) -> None:
        self.assertEqual(
            resolve_candidate({"best_format": "pdf", "url": "https://x/a.xml"}),
            "jats",
        )
        self.assertIsNone(resolve_candidate({"url": "https://x/a.bin"}))


if __name__ == "__main__":
    unittest.main()
