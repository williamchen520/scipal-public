"""N3 thin adapter tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from services.pipeline.builtin import HtmlParserAdapter, HtmlQualityGate, PaperSink
from services.pipeline.contracts import ParserAdapter, ReviewGate, Sink, SourceRef
from services.pipeline.registry import AdapterRegistry, build_default_registry


class PipelineAdapterTests(unittest.TestCase):
    def test_default_registry_resolves(self) -> None:
        registry = build_default_registry()
        self.assertTrue(isinstance(registry.parser_for("html"), ParserAdapter))
        self.assertTrue(isinstance(registry.parser_for("jats"), ParserAdapter))
        self.assertTrue(isinstance(registry.gate_for("html"), ReviewGate))
        self.assertTrue(isinstance(registry.sink_for("paper"), Sink))

    def test_html_parser_and_gate(self) -> None:
        fixture = Path(__file__).resolve().parent / "fixtures" / "html" / "nature.html"
        payload = HtmlParserAdapter().parse(
            SourceRef(fixture, "html", "https://www.nature.com/articles/x")
        )
        self.assertEqual(payload["publisher"], "nature")
        result = HtmlQualityGate().evaluate(payload)
        self.assertFalse(result.ok)

    def test_paper_sink_calls_build(self) -> None:
        with mock.patch(
            "services.pipeline.builtin.build_paper",
            return_value={"paper_id": "p1", "paragraphs": 1},
        ) as build:
            result = PaperSink().write(
                {"title": "x"}, {"paper_id": "p1", "source_kind": "html"}
            )
        self.assertEqual(result["paper_id"], "p1")
        build.assert_called_once()

    def test_missing_parser_raises(self) -> None:
        with self.assertRaises(KeyError):
            AdapterRegistry().parser_for("pdf")


if __name__ == "__main__":
    unittest.main()
