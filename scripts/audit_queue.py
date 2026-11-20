#!/usr/bin/env python3
"""Print the local audit exception queue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.audit.queue import list_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    rows = list_events(args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['created_at']} {row['source']} {row['reasons']} {row['query'][:80]}")
        print(f"events={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
