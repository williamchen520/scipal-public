"""N3 thin adapter layer."""

from services.pipeline.contracts import ParserAdapter, ReviewGate, Sink, SourceRef
from services.pipeline.registry import DEFAULT_REGISTRY, AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "DEFAULT_REGISTRY",
    "ParserAdapter",
    "ReviewGate",
    "Sink",
    "SourceRef",
]
