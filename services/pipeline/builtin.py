"""Built-in thin adapters used by the import lanes."""

from __future__ import annotations

from typing import Any

from services.imports.code_build import build_code
from services.imports.html_quality import QualityResult, evaluate_html
from services.imports.paper_build import build_paper
from services.papers.html_parser import parse_html
from services.papers.md_parser import parse_markdown
from services.pipeline.contracts import SourceRef


class HtmlParserAdapter:
    name = "html"
    source_kind = "html"

    def parse(self, source: SourceRef) -> dict[str, Any]:
        return parse_html(source.path.read_bytes(), source_url=source.source_uri)


class JatsParserAdapter:
    name = "jats"
    source_kind = "jats"

    def parse(self, source: SourceRef) -> dict[str, Any]:
        from services.imports.paper_lane import parse_jats

        return parse_jats(source.path)


class MarkdownParserAdapter:
    name = "md"
    source_kind = "md"

    def parse(self, source: SourceRef) -> dict[str, Any]:
        return parse_markdown(source.path, source_uri=source.source_uri)


class HtmlQualityGate:
    name = "html_quality"

    def evaluate(self, payload: dict[str, Any]) -> QualityResult:
        return evaluate_html(payload)


class PaperSink:
    name = "paper"

    def write(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return build_paper(
            context["paper_id"],
            payload,
            source_kind=context.get("source_kind") or "html",
            source_uri=context.get("source_uri") or "",
        )


class CodeSink:
    name = "code"

    def write(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return build_code(context["item"], payload)
