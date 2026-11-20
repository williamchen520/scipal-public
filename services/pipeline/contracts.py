"""Thin pipeline contracts: parse, review, sink."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class SourceRef:
    path: Path
    source_kind: str
    source_uri: str = ""


@runtime_checkable
class ParserAdapter(Protocol):
    name: str
    source_kind: str

    def parse(self, source: SourceRef) -> dict[str, Any]: ...


@runtime_checkable
class ReviewGate(Protocol):
    def evaluate(self, payload: dict[str, Any]) -> Any: ...


@runtime_checkable
class Sink(Protocol):
    def write(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...
