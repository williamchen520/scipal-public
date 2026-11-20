#!/usr/bin/env python3
"""Repair citation DOIs from raw reference text (dry-run by default)."""

from __future__ import annotations

import argparse
import re

DOI = re.compile(r"(?<![\w.])(10\.\d{4,}/[A-Za-z0-9\-._()]+)", re.IGNORECASE)


def extract_doi(text: str) -> str:
    match = DOI.search(text or "")
    if not match:
        return ""
    value = match.group(1)
    if value.count("(") != value.count(")"):
        return ""
    return value.rstrip(".,;)]").lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    import psycopg

    changed = 0
    with psycopg.connect(args.dsn) as conn:
        rows = conn.execute(
            "SELECT citation_id,doi,raw_text FROM citations "
            "WHERE raw_text IS NOT NULL AND btrim(raw_text)<>''"
        ).fetchall()
        updates = []
        for citation_id, old, raw in rows:
            new = extract_doi(raw)
            if new and new != (old or "").strip().lower():
                updates.append((citation_id, old or "", new))
        print(f"scanned={len(rows)} would_update={len(updates)} apply={args.apply}")
        if args.apply and updates:
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE citations SET doi=%s WHERE citation_id=%s",
                    [(new, citation_id) for citation_id, _, new in updates],
                )
            conn.commit()
            changed = len(updates)
    print(f"updated={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
