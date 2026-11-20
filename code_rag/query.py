"""Parse explicit code-search query prefixes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedQuery:
    query: str
    mode: str = ""
    language: str = ""
    path_filter: str = ""


def parse_query(text: str) -> ParsedQuery:
    query = (text or "").strip()
    if not query:
        return ParsedQuery("")
    for prefix, field in (("re:", "mode"), ("sym:", "mode")):
        if query.lower().startswith(prefix):
            remainder = query[len(prefix) :].strip()
            if field == "mode":
                return ParsedQuery(remainder, mode="regex")
    if query.lower().startswith("path:"):
        rest = query[5:].strip()
        value, _, remainder = rest.partition(" ")
        return ParsedQuery(remainder.strip(), path_filter=value)
    if query.lower().startswith("lang:"):
        rest = query[5:].strip()
        value, _, remainder = rest.partition(" ")
        return ParsedQuery(remainder.strip(), language=value)
    return ParsedQuery(query)
