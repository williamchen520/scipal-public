#!/usr/bin/env python3
"""Audit whether citation records can form a usable local relation graph."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def normalize_doi(value: str) -> str:
    text = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", (value or "").strip(), flags=re.I)
    return text.strip().lower()


def audit(dsn: str) -> dict:
    import psycopg

    with psycopg.connect(dsn) as conn:
        total = conn.execute("SELECT count(*) FROM citations").fetchone()[0]
        with_doi = conn.execute(
            "SELECT count(*) FROM citations WHERE doi IS NOT NULL AND btrim(doi)<>''"
        ).fetchone()[0]
        papers = conn.execute("SELECT count(*) FROM papers").fetchone()[0]
        papers_doi = conn.execute(
            "SELECT count(*) FROM papers WHERE doi IS NOT NULL AND btrim(doi)<>''"
        ).fetchone()[0]
        exact = conn.execute(
            "SELECT count(*) FROM citations c JOIN papers p "
            "ON lower(btrim(c.doi))=lower(btrim(p.doi)) "
            "WHERE c.doi IS NOT NULL AND btrim(c.doi)<>''"
        ).fetchone()[0]
        title_exact = conn.execute(
            "SELECT count(*) FROM citations c JOIN papers p "
            "ON lower(btrim(c.title))=lower(btrim(p.title)) "
            "WHERE c.title IS NOT NULL AND btrim(c.title)<>''"
        ).fetchone()[0]
        papers_dois = [row[0] for row in conn.execute(
            "SELECT lower(btrim(doi)) FROM papers WHERE doi IS NOT NULL AND btrim(doi)<>''"
        )]
        prefixes: dict[str, set[str]] = {}
        for doi in papers_dois:
            for size in range(12, len(doi) + 1):
                prefixes.setdefault(doi[:size], set()).add(doi)
        lengths = Counter()
        prefix_hits = 0
        for (doi,) in conn.execute(
            "SELECT doi FROM citations WHERE doi IS NOT NULL AND btrim(doi)<>''"
        ):
            doi = normalize_doi(doi)
            lengths[len(doi)] += 1
            if doi in prefixes:
                prefix_hits += 1
    return {
        "citations": total,
        "citations_with_doi": with_doi,
        "papers": papers,
        "papers_with_doi": papers_doi,
        "exact_doi_join": exact,
        "exact_title_join": title_exact,
        "prefix_doi_hits": prefix_hits,
        "doi_lengths": dict(sorted(lengths.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit(args.dsn)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
