"""Independent code-rag service skeleton.

No Flask import, no literature corpus connection. P1 only provides health
and schema status; search/indexing land in later phases.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg

SCHEMA_VERSION = 1


def dsn() -> str:
    value = (
        os.environ.get("SCIPAL_CODE_DSN", "").strip()
        or os.environ.get("SCIPAL_CODE_READ_DSN", "").strip()
    )
    if not value:
        raise SystemExit("SCIPAL_CODE_DSN or SCIPAL_CODE_READ_DSN is required")
    return value


def connect():
    return psycopg.connect(dsn())


def health(conn=None) -> dict[str, Any]:
    own = conn is None
    conn = conn or connect()
    try:
        version = conn.execute(
            "SELECT version FROM code_rag.schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        units = conn.execute("SELECT count(*) FROM code_rag.code_units").fetchone()[0]
        indexable = conn.execute(
            "SELECT count(*) FROM code_rag.code_units WHERE unit_type <> 'file'"
        ).fetchone()[0]
        missing = conn.execute(
            "SELECT count(*) FROM code_rag.code_units u "
            "LEFT JOIN code_rag.code_embeddings e ON e.unit_id=u.unit_id "
            "WHERE u.unit_type <> 'file' AND e.unit_id IS NULL"
        ).fetchone()[0]
        active = conn.execute(
            "SELECT count(*) FROM code_rag.code_snapshots WHERE is_active"
        ).fetchone()[0]
        snapshots = conn.execute("SELECT count(*) FROM code_rag.code_snapshots").fetchone()[0]
        libraries = conn.execute(
            "SELECT count(DISTINCT library_id) FROM code_rag.code_sources"
        ).fetchone()[0]
        indexed = max(0, indexable - missing)
        return {
            "ok": bool(version and version[0] == SCHEMA_VERSION and missing == 0),
            "module_id": "code",
            "schema_version": version[0] if version else None,
            "expected_schema_version": SCHEMA_VERSION,
            "libraries": libraries,
            "snapshots": snapshots,
            "units": units,
            "active_snapshots": active,
            "missing_embeddings": missing,
            "indexable_units": indexable,
            "embedding_coverage": round(indexed / max(indexable, 1), 4),
            "degraded": missing > 0,
        }
    finally:
        if own:
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["health"], nargs="?", default="health")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "health":
        result = health()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
