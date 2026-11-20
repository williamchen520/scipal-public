#!/usr/bin/env python3
"""Check a polished manuscript against protected spans before accepting it."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

CITATION_PATTERNS = [
    re.compile(r"\[[0-9][0-9,\-– ]*\]"),
    re.compile(r"\([A-Z][A-Za-z\-]+ et al\.,? \d{4}\)"),
    re.compile(r"\\cite\{[^}]+\}"),
]
NUMBER_RE = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s?(?:%|mg|g|kg|mL|L|µM|μM|nM|mM|kb|bp|Da|kDa|h|hours|days|weeks|months|years))?\b"
)
HEDGES = ["may", "might", "could", "suggest", "suggests", "associated", "correlat", "preliminary", "consistent with"]
CAUSAL = ["causes", "caused", "induces", "induced", "proves", "proven", "demonstrates", "confirms"]


def citations(text: str) -> list[str]:
    found = []
    for pattern in CITATION_PATTERNS:
        found.extend(pattern.findall(text))
    return found


def numbers(text: str) -> list[str]:
    return NUMBER_RE.findall(text)


def hedges(text: str) -> list[str]:
    lowered = text.lower()
    return [term for term in HEDGES if term in lowered]


def causal(text: str) -> list[str]:
    lowered = text.lower()
    return [term for term in CAUSAL if term in lowered]


def check(original: str, polished: str) -> dict:
    old_cites, new_cites = citations(original), citations(polished)
    old_numbers, new_numbers = numbers(original), numbers(polished)
    old_hedges, new_hedges = hedges(original), hedges(polished)
    old_causal, new_causal = causal(original), causal(polished)
    issues = []
    if old_cites != new_cites:
        issues.append("citations changed or reordered")
    if Counter(old_numbers) != Counter(new_numbers):
        issues.append("numbers/units changed")
    if len(new_hedges) < len(old_hedges):
        issues.append("hedges removed")
    if len(new_causal) > len(old_causal):
        issues.append("causal language strengthened")
    return {
        "ok": not issues,
        "issues": issues,
        "citations": {"original": old_cites, "polished": new_cites},
        "numbers": {"original": old_numbers, "polished": new_numbers},
        "hedges": {"original": old_hedges, "polished": new_hedges},
        "causal": {"original": old_causal, "polished": new_causal},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True)
    parser.add_argument("--polished", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = check(
        Path(args.original).read_text(encoding="utf-8"),
        Path(args.polished).read_text(encoding="utf-8"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
