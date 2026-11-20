"""Evaluate query-aware repository maps on file-level targets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from code_rag.repomap import build_repomap


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-tokens", type=int, default=400)
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        result = build_repomap(
            library_id=case["library_id"],
            query=case["query"],
            max_tokens=args.max_tokens,
            dsn=args.dsn,
        )
        paths = [item["path"] for item in result.get("files", [])]
        rank = paths.index(case["expected_path"]) + 1 if case["expected_path"] in paths else None
        rows.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected_path": case["expected_path"],
                "rank": rank,
                "top": paths[:3],
            }
        )
    hit1 = sum(1 for row in rows if row["rank"] == 1) / max(len(rows), 1)
    hit3 = sum(1 for row in rows if row["rank"] and row["rank"] <= 3) / max(len(rows), 1)
    output = {"cases": len(rows), "file_hit@1": hit1, "file_hit@3": hit3, "rows": rows}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
