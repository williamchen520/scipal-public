#!/usr/bin/env python3
"""Consume audit_outbox with SKIP LOCKED. No LLM handler wired yet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.audit.outbox import claim, complete, fail
from services.audit.error_lifecycle import transition as transition_error
from services.audit.regen_handler import handle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--stale-seconds", type=int, default=300)
    args = parser.parse_args()
    jobs = claim(args.limit, max_attempts=args.max_attempts, stale_seconds=args.stale_seconds)
    for job in jobs:
        try:
            result = handle(job)
            complete(job["id"], status="done")
            print(f"done id={job['id']} new={result['ledger']['answer_id']}")
        except Exception as exc:  # noqa: BLE001
            status = fail(job["id"], last_error=str(exc)[:1000], max_attempts=args.max_attempts)
            if status == "unresolved":
                try:
                    transition_error(job["error_id"], "unresolved", note=str(exc)[:500], actor="outbox")
                except Exception:
                    pass
            print(f"{status} id={job['id']} reason={exc}")
    print(f"claimed={len(jobs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
