"""Export wrong/missing search feedback as regression cases."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN", "") or os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--output", default="eval/code_rag_stack/feedback_bad_cases.json")
    parser.add_argument("--library-id", action="append", default=[])
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    with psycopg.connect(args.dsn) as conn:
        rows = conn.execute(
            "SELECT e.event_id,e.library_id,e.query,e.mode,e.top_path,e.created_at,"
            "f.verdict,f.expected_path,f.note "
            "FROM code_rag.search_feedback f JOIN code_rag.search_events e ON e.event_id=f.event_id "
            "WHERE f.verdict IN ('wrong','missing') AND (%s::text[] = '{}' OR e.library_id = ANY(%s)) "
            "ORDER BY f.created_at DESC",
            (args.library_id, args.library_id),
        ).fetchall()
    cases = [
        {
            "event_id": row[0],
            "library_id": row[1],
            "query": row[2],
            "mode": row[3],
            "top_path": row[4],
            "created_at": row[5].isoformat(),
            "verdict": row[6],
            "expected_path": row[7],
            "note": row[8],
        }
        for row in rows
    ]
    Path(args.output).write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FEEDBACK_EXPORT_OK cases={len(cases)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
