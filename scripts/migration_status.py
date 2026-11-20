#!/usr/bin/env python3
"""Check migration lock checksums and optionally record staging versions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = ROOT / "deploy/migrations.lock.json"


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(lock: Path = DEFAULT_LOCK, root: Path = ROOT) -> list[str]:
    data = json.loads(lock.read_text(encoding="utf-8"))
    errors = []
    for item in data.get("migrations", []):
        rel = str(item.get("file") or "")
        expected = str(item.get("sha256") or "")
        path = root / rel
        if not path.exists():
            errors.append(f"missing: {rel}")
        elif checksum(path) != expected:
            errors.append(f"checksum drift: {rel}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", default=str(DEFAULT_LOCK))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors = check(Path(args.lock))
    data = json.loads(Path(args.lock).read_text(encoding="utf-8"))
    result = {"migrations": len(data.get("migrations", [])), "errors": errors, "ok": not errors}
    if args.dsn:
        import psycopg

        with psycopg.connect(args.dsn) as pg:
            if args.record:
                pg.execute(
                    "CREATE TABLE IF NOT EXISTS public.scipal_schema_migrations "
                    "(version text PRIMARY KEY, sha256 text NOT NULL, "
                    "applied_at timestamptz NOT NULL DEFAULT now())"
                )
                for item in data.get("migrations", []):
                    pg.execute(
                        "INSERT INTO public.scipal_schema_migrations(version, sha256) "
                        "VALUES (%s,%s) ON CONFLICT (version) DO NOTHING",
                        (item["version"], item["sha256"]),
                    )
                pg.commit()
            table = pg.execute(
                "SELECT to_regclass('public.scipal_schema_migrations')"
            ).fetchone()[0]
            if table:
                rows = pg.execute(
                    "SELECT version, sha256, applied_at FROM public.scipal_schema_migrations "
                    "ORDER BY version"
                ).fetchall()
                result["applied"] = [
                    {"version": r[0], "sha256": r[1], "applied_at": r[2].isoformat()} for r in rows
                ]
            else:
                result["applied"] = []
                result["note"] = "schema migration table not initialized"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"migrations={result['migrations']} errors={len(errors)}")
        for error in errors:
            print(f"ERROR {error}")
        print("OK" if not errors else "FAILED")
        for row in result.get("applied", []):
            print(f"APPLIED {row['version']} {row['applied_at']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
