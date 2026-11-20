#!/usr/bin/env python3
"""Build a human labeling worksheet from extracted citation contexts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

FIELDS = [
    "citation_id",
    "citing_paper_id",
    "ref_number",
    "cited_doi",
    "cited_title",
    "section",
    "sentence",
    "context",
    "sentiment",
    "notes",
]


def sample(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or len(rows) <= limit:
        return rows
    step = len(rows) / limit
    picked = []
    seen = set()
    for index in range(limit):
        row = rows[min(len(rows) - 1, int(index * step))]
        key = (row.get("citation_id"), row.get("char_start"), row.get("char_end"))
        if key in seen:
            continue
        seen.add(key)
        picked.append(row)
    return picked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="artifacts/scinet-lite-contexts.jsonl")
    parser.add_argument("--out", default="artifacts/scinet-lite-labeling.csv")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in Path(args.input).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    picked = sample(rows, args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in picked:
            row = dict(row)
            row.setdefault("sentiment", "")
            row.setdefault("notes", "")
            writer.writerow(row)
    print(f"input={len(rows)} sampled={len(picked)} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
