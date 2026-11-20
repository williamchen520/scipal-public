"""Auditable query alias table for code search."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_aliases() -> tuple[dict[str, tuple[str, ...]], dict]:
    path = Path(__file__).with_name("aliases.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    table: dict[str, tuple[str, ...]] = {}
    for row in payload.get("aliases", []):
        phrase = str(row.get("phrase", "")).strip().lower()
        terms = tuple(str(term).strip() for term in row.get("aliases", []) if str(term).strip())
        if phrase and terms:
            table[phrase] = terms
    return table, payload


def expand_query(query: str) -> str:
    table, _ = load_aliases()
    lower = query.lower()
    additions = []
    for phrase, terms in table.items():
        if phrase in lower:
            additions.extend(terms)
    return query + (" " + " ".join(additions) if additions else "")


def alias_rows() -> list[dict]:
    _, payload = load_aliases()
    return list(payload.get("aliases", []))
