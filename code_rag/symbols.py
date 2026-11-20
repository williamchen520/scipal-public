"""Symbol normalization and symbol-index helpers."""

from __future__ import annotations

import re


def normalize_symbol(name: str) -> str:
    """Lowercase and split camelCase/snake_case/kebab-case into terms."""
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name or "")
    value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    return " ".join(value.lower().split())


def symbol_terms(name: str) -> set[str]:
    return {term for term in normalize_symbol(name).split() if len(term) >= 2}
