"""In-memory adapter registry (no entry points, no marketplace)."""

from __future__ import annotations

from typing import Any

from services.pipeline.builtin import (
    CodeSink,
    HtmlParserAdapter,
    HtmlQualityGate,
    JatsParserAdapter,
    MarkdownParserAdapter,
    PaperSink,
)
from services.pipeline.contracts import ParserAdapter, ReviewGate, Sink


class AdapterRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, ParserAdapter] = {}
        self._gates: dict[str, ReviewGate] = {}
        self._sinks: dict[str, Sink] = {}

    def register_parser(self, parser: ParserAdapter) -> None:
        self._parsers[parser.source_kind] = parser

    def register_gate(self, kind: str, gate: ReviewGate) -> None:
        self._gates[kind] = gate

    def register_sink(self, sink: Sink) -> None:
        self._sinks[sink.name] = sink

    def parser_for(self, source_kind: str) -> ParserAdapter:
        parser = self._parsers.get(source_kind)
        if parser is None:
            raise KeyError(f"no parser for {source_kind}")
        return parser

    def gate_for(self, source_kind: str) -> ReviewGate | None:
        return self._gates.get(source_kind)

    def sink_for(self, name: str) -> Sink:
        sink = self._sinks.get(name)
        if sink is None:
            raise KeyError(f"no sink for {name}")
        return sink


def build_default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register_parser(HtmlParserAdapter())
    registry.register_parser(JatsParserAdapter())
    registry.register_parser(MarkdownParserAdapter())
    registry.register_gate("html", HtmlQualityGate())
    registry.register_gate("md", HtmlQualityGate())
    registry.register_sink(PaperSink())
    registry.register_sink(CodeSink())
    return registry


DEFAULT_REGISTRY = build_default_registry()
