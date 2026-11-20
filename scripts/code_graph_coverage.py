"""W2 graph coverage report: classify unresolved imports as external vs internal."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_rag.resolve import load, module_of, resolve_import_target


def report(conn, library_id: str) -> dict:
    files, units = load(conn, library_id, "")
    file_by_module = {module_of(path): path for path in files}
    rows = conn.execute(
        "SELECT e.src_unit_id,e.dst_unit_id,u.path FROM code_rag.code_edges e "
        "JOIN code_rag.code_units su ON su.unit_id=e.src_unit_id "
        "JOIN code_rag.code_files u ON u.file_id=su.file_id "
        "WHERE e.library_id=%s AND e.relation='imports'",
        (library_id,),
    ).fetchall()
    resolved = 0
    unresolved_internal = 0
    external = 0
    cross_language = 0
    for src, dst, path in rows:
        if not str(dst).startswith("unresolved:"):
            resolved += 1
            continue
        if str(dst).startswith("unresolved:cross_language:"):
            cross_language += 1
            continue
        if resolve_import_target(source_path=path, target=dst, file_by_module=file_by_module):
            unresolved_internal += 1
        else:
            external += 1
    internal_total = resolved + unresolved_internal
    return {
        "library_id": library_id,
        "imports_total": len(rows),
        "imports_resolved": resolved,
        "unresolved_internal": unresolved_internal,
        "external": external,
        "cross_language": cross_language,
        "internal_coverage": round(resolved / internal_total, 4) if internal_total else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN", "") or os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--output", default="eval/code_rag_stack/graph_coverage.json")
    parser.add_argument("--library-id", action="append", default=[])
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    with psycopg.connect(args.dsn) as conn:
        libraries = args.library_id or [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT library_id FROM code_rag.code_files ORDER BY library_id"
            ).fetchall()
        ]
        results = [report(conn, library_id) for library_id in libraries]
    output = {"libraries": results}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in results:
        print(
            item["library_id"],
            f"internal={item['internal_coverage']}",
            f"resolved={item['imports_resolved']}",
            f"internal_unresolved={item['unresolved_internal']}",
            f"external={item['external']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
