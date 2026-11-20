"""One DOI parser for corpus ingestion.

The old per-parser regexes disagreed about parentheses: JATS/GROBID stopped at
``(``, so DOIs like ``10.1016/S1097-2765(02)00470-7`` were truncated.
"""

from __future__ import annotations

import re

# Stop at clearly non-DOI delimiters, but keep parentheses inside the DOI.
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s;,\]\"<>]+", re.IGNORECASE)

_TRAILING = ".,;:"


def extract_doi(text: str) -> str:
    """Return a normalized DOI or ''.

    Rules:
    - strip URL/``doi:`` prefixes by matching from ``10.``
    - strip trailing sentence punctuation
    - preserve balanced parentheses
    - reject unbalanced parentheses (truncated source text)
    """
    match = DOI_RE.search(text or "")
    if not match:
        return ""
    value = match.group(0).rstrip(_TRAILING)
    while value.endswith(")") and value.count(")") > value.count("("):
        value = value[:-1].rstrip(_TRAILING)
    if value.count("(") != value.count(")"):
        return ""
    return value.lower()
