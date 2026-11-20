"""Audit code graph edges without claiming that external calls are resolvable."""

from __future__ import annotations

import argparse
import json
import os

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--snapshot-id", default="")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    with psycopg.connect(args.dsn) as conn:
        snapshot = args.snapshot_id or (
            conn.execute(
                "SELECT snapshot_id FROM code_rag.code_snapshots "
                "WHERE library_id=%s AND is_active LIMIT 1",
                (args.library_id,),
            ).fetchone() or ("",)
        )[0]
        rows = conn.execute(
            "SELECT relation, "
            "count(*) AS total, "
            "count(*) FILTER (WHERE dst_unit_id LIKE 'unresolved:%%') AS unresolved, "
            "count(*) FILTER (WHERE dst_unit_id LIKE 'unit_%%') AS resolved "
            "FROM code_rag.code_edges e "
            "JOIN code_rag.code_units su ON su.unit_id=e.src_unit_id "
            "WHERE e.library_id=%s AND su.snapshot_id=%s "
            "GROUP BY relation ORDER BY relation",
            (args.library_id, snapshot),
        ).fetchall()
        cross = conn.execute(
            "SELECT count(*) FROM code_rag.code_edges e "
            "JOIN code_rag.code_units s ON s.unit_id=e.src_unit_id "
            "JOIN code_rag.code_units d ON d.unit_id=e.dst_unit_id "
            "JOIN code_rag.code_files sf ON sf.file_id=s.file_id "
            "JOIN code_rag.code_files df ON df.file_id=d.file_id "
            "WHERE e.library_id=%s AND s.snapshot_id=%s AND sf.path <> df.path",
            (args.library_id, snapshot),
        ).fetchone()[0]
    result = {
        "library_id": args.library_id,
        "snapshot_id": snapshot,
        "cross_file_edges": cross,
        "relations": {
            row[0]: {"total": row[1], "unresolved": row[2], "resolved": row[3]}
            for row in rows
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
