#!/usr/bin/env python3
"""Backfill the independent code_symbols index from code_units."""

from __future__ import annotations

import argparse
import os

import psycopg

from code_rag.symbols import normalize_symbol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--library-id", default="")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")
    where = "WHERE u.library_id=%s" if args.library_id else ""
    params = (args.library_id,) if args.library_id else ()
    with psycopg.connect(args.dsn) as conn:
        rows = conn.execute(
            "SELECT u.unit_id,u.library_id,u.snapshot_id,u.symbol_name,u.unit_type,"
            "u.start_line,u.end_line,f.path "
            "FROM code_rag.code_units u JOIN code_rag.code_files f ON f.file_id=u.file_id "
            f"{where}",
            params,
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO code_rag.code_symbols "
                "(unit_id,library_id,snapshot_id,symbol_name,normalized_name,path,"
                "unit_type,start_line,end_line) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (unit_id) DO UPDATE SET "
                "symbol_name=EXCLUDED.symbol_name, normalized_name=EXCLUDED.normalized_name, "
                "path=EXCLUDED.path",
                (
                    row[0], row[1], row[2], row[3], normalize_symbol(row[3]),
                    row[7], row[4], row[5], row[6],
                ),
            )
        conn.commit()
    print(f"CODE_SYMBOLS_REBUILT units={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
