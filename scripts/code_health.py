"""Index health check for code RAG libraries."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_rag.resolve import load, module_of, resolve_import_target

BM25_TABLE = "public.code_units_bm25"


def graph_internal_coverage(conn, library_id: str) -> tuple[int, int, float | None]:
    files, _ = load(conn, library_id, "")
    file_by_module = {module_of(path): path for path in files}
    rows = conn.execute(
        "SELECT e.dst_unit_id, u.path FROM code_rag.code_edges e "
        "JOIN code_rag.code_units su ON su.unit_id=e.src_unit_id "
        "JOIN code_rag.code_files u ON u.file_id=su.file_id "
        "WHERE e.library_id=%s AND e.relation='imports'",
        (library_id,),
    ).fetchall()
    resolved = unresolved_internal = 0
    for dst, path in rows:
        if not str(dst).startswith("unresolved:"):
            resolved += 1
        elif resolve_import_target(source_path=path, target=dst, file_by_module=file_by_module):
            unresolved_internal += 1
    total = resolved + unresolved_internal
    return resolved, unresolved_internal, (round(resolved / total, 4) if total else None)


def check_library(code_conn, bm25_conn, row, max_age_days: float, skip_graph: bool) -> dict:
    library_id, snapshot_id, commit, created_at = row
    now = datetime.now(timezone.utc)
    age_days = round((now - created_at).total_seconds() / 86400, 1) if created_at else None
    units = code_conn.execute(
        "SELECT count(*) FROM code_rag.code_units WHERE library_id=%s AND snapshot_id=%s "
        "AND unit_type <> 'file'",
        (library_id, snapshot_id),
    ).fetchone()[0]
    files = code_conn.execute(
        "SELECT count(*) FROM code_rag.code_files WHERE library_id=%s AND snapshot_id=%s",
        (library_id, snapshot_id),
    ).fetchone()[0]
    symbols = code_conn.execute(
        "SELECT count(*) FROM code_rag.code_symbols WHERE library_id=%s AND snapshot_id=%s",
        (library_id, snapshot_id),
    ).fetchone()[0]
    bm25_units = bm25_conn.execute(
        f"SELECT count(*) FROM {BM25_TABLE} WHERE library_id=%s AND snapshot_id=%s",
        (library_id, snapshot_id),
    ).fetchone()[0]
    resolved = unresolved_internal = 0
    internal_coverage = None
    if not skip_graph:
        resolved, unresolved_internal, internal_coverage = graph_internal_coverage(code_conn, library_id)
    errors = []
    warnings = []
    if units <= 0:
        errors.append("no_units")
    if bm25_units != units:
        errors.append(f"bm25_mismatch:{bm25_units}!={units}")
    if age_days is not None and age_days > max_age_days:
        errors.append(f"stale:{age_days}d>{max_age_days}d")
    if internal_coverage is not None and internal_coverage < 0.98:
        warnings.append(f"internal_coverage:{internal_coverage}")
    return {
        "library_id": library_id,
        "snapshot_id": snapshot_id,
        "commit": commit,
        "age_days": age_days,
        "units": units,
        "files": files,
        "symbols": symbols,
        "bm25_units": bm25_units,
        "bm25_delta": bm25_units - units,
        "resolved_imports": resolved,
        "internal_unresolved": unresolved_internal,
        "internal_coverage": internal_coverage,
        "status": "FAIL" if errors else ("WARN" if warnings else "PASS"),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN", "") or os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--bm25-dsn", default=os.environ.get("SCIPAL_CODE_BM25_DSN", ""))
    parser.add_argument("--library-id", action="append", default=[])
    parser.add_argument("--max-age-days", type=float, default=30)
    parser.add_argument("--skip-graph", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if not args.code_dsn or not args.bm25_dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN and SCIPAL_CODE_BM25_DSN are required")
    with psycopg.connect(args.code_dsn) as code_conn, psycopg.connect(args.bm25_dsn) as bm25_conn:
        rows = code_conn.execute(
            "SELECT library_id,snapshot_id,commit_sha,created_at FROM code_rag.code_snapshots "
            "WHERE is_active AND (%s::text[] = '{}' OR library_id = ANY(%s)) "
            "ORDER BY library_id",
            (args.library_id, args.library_id),
        ).fetchall()
        results = [
            check_library(code_conn, bm25_conn, row, args.max_age_days, args.skip_graph)
            for row in rows
        ]
    payload = {"libraries": results}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in results:
        print(
            f"{item['status']} {item['library_id']} units={item['units']} "
            f"bm25={item['bm25_units']} coverage={item['internal_coverage']} "
            f"age={item['age_days']}d {','.join(item['errors'] + item['warnings'])}"
        )
    return 1 if any(item["status"] == "FAIL" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
