"""BM25 code search backend backed by ParadeDB pg_search."""

from __future__ import annotations

import os
from typing import Any

import psycopg

TABLE = "public.code_units_bm25"


def _dsn() -> str:
    value = os.environ.get("SCIPAL_CODE_BM25_DSN", "").strip()
    if not value:
        raise RuntimeError("SCIPAL_CODE_BM25_DSN is required")
    return value


def ensure_schema(conn) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} ("
        "unit_id text PRIMARY KEY, library_id text NOT NULL, snapshot_id text NOT NULL, "
        "symbol_name text NOT NULL DEFAULT '', path text NOT NULL DEFAULT '', "
        "unit_type text NOT NULL DEFAULT 'code', start_line integer NOT NULL DEFAULT 0, "
        "end_line integer NOT NULL DEFAULT 0, text text NOT NULL)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS code_units_bm25_idx ON {TABLE} "
        "USING bm25 (unit_id, text, symbol_name, path) WITH (key_field='unit_id')"
    )


def sync_library(*, code_dsn: str, library_id: str, snapshot_id: str = "", bm25_dsn: str = "") -> dict[str, Any]:
    bm25_dsn = bm25_dsn or _dsn()
    with psycopg.connect(code_dsn) as code, psycopg.connect(bm25_dsn) as bm:
        ensure_schema(bm)
        if not snapshot_id:
            row = code.execute(
                "SELECT snapshot_id FROM code_rag.code_snapshots "
                "WHERE library_id=%s AND is_active LIMIT 1",
                (library_id,),
            ).fetchone()
            snapshot_id = row[0] if row else ""
        rows = code.execute(
            "SELECT u.unit_id,u.symbol_name,u.unit_type,u.start_line,u.end_line,f.path,u.text "
            "FROM code_rag.code_units u JOIN code_rag.code_files f ON f.file_id=u.file_id "
            "WHERE u.library_id=%s AND u.snapshot_id=%s AND u.unit_type <> 'file'",
            (library_id, snapshot_id),
        ).fetchall()
        bm.execute(f"DELETE FROM {TABLE} WHERE library_id=%s", (library_id,))
        with bm.cursor().copy(
            f"COPY {TABLE} (unit_id,library_id,snapshot_id,symbol_name,path,unit_type,"
            "start_line,end_line,text) FROM STDIN"
        ) as copy:
            for row in rows:
                copy.write_row(
                    (
                        row[0], library_id, snapshot_id, row[1], row[5], row[2],
                        row[3], row[4], row[6],
                    )
                )
        bm.commit()
    return {"library_id": library_id, "snapshot_id": snapshot_id, "units": len(rows)}


def search_bm25(
    query: str,
    *,
    library_id: str,
    top_k: int = 10,
    snapshot_id: str = "",
    dsn: str = "",
) -> list[dict[str, Any]]:
    dsn = dsn or _dsn()
    query = (query or "").strip()[:1000]
    if not query:
        return []
    with psycopg.connect(dsn) as conn:
        if not snapshot_id:
            row = conn.execute(
                f"SELECT snapshot_id FROM {TABLE} WHERE library_id=%s LIMIT 1",
                (library_id,),
            ).fetchone()
            snapshot_id = row[0] if row else ""
        rows = conn.execute(
            f"SELECT unit_id,symbol_name,path,unit_type,left(text,500),start_line,end_line,"
            f"pdb.score(unit_id) AS score FROM {TABLE} "
            "WHERE text @@@ pdb.match(%s, NULL, 0, false, false, false) "
            "AND library_id=%s AND (%s='' OR snapshot_id=%s) "
            "ORDER BY pdb.score(unit_id) * "
            "CASE WHEN path LIKE 'tests/%%' OR path LIKE 'test/%%' THEN 0.35 ELSE 1.0 END DESC "
            "LIMIT %s",
            (query, library_id, snapshot_id, snapshot_id, max(1, min(int(top_k), 100))),
        ).fetchall()
    return [
        {
            "unit_id": row[0],
            "library_id": library_id,
            "snapshot_id": snapshot_id,
            "symbol_name": row[1],
            "unit_type": row[3],
            "snippet": row[4] or "",
            "start_line": row[5],
            "end_line": row[6],
            "path": row[2],
            "score": float(row[7]),
        }
        for row in rows
    ]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--snapshot-id", default="")
    parser.add_argument("--code-dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--bm25-dsn", default="")
    args = parser.parse_args()
    if not args.code_dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")
    result = sync_library(
        code_dsn=args.code_dsn,
        library_id=args.library_id,
        snapshot_id=args.snapshot_id,
        bm25_dsn=args.bm25_dsn,
    )
    print(f"BM25_SYNC_OK library={result['library_id']} units={result['units']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
