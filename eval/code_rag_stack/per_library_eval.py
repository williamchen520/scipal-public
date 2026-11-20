"""Evaluate per-library retrieval on the generated smoke set."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path

from code_rag.search import search


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="eval/code_rag_stack/per_library_10.json")
    parser.add_argument("--output", default="eval/code_rag_stack/per_library_10_result.json")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--backend", choices=["hybrid", "bm25", "bm25_map", "coderag"], default="hybrid")
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        started = time.perf_counter()
        if args.backend == "bm25":
            from code_rag.bm25 import search_bm25
            hits = search_bm25(case["query"], library_id=case["library_id"], top_k=args.top_k)
        elif args.backend == "bm25_map":
            from code_rag.rerank import search_bm25_map
            hits = search_bm25_map(case["query"], library_id=case["library_id"], top_k=args.top_k)
        elif args.backend == "hybrid":
            from code_rag.hybrid import search_hybrid
            hits = search_hybrid(case["query"], library_id=case["library_id"], top_k=args.top_k)
        else:
            hits = search(case["query"], library_id=case["library_id"], top_k=args.top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        paths = [hit["path"] for hit in hits]
        symbols = [hit["symbol_name"] for hit in hits]
        expected_paths = case.get("expected_paths") or [case["expected_path"]]
        ranks = [paths.index(path) + 1 for path in expected_paths if path in paths]
        file_rank = min(ranks) if ranks else None
        expected_symbol = str(case.get("expected_symbol") or "")
        symbol_rank = (
            symbols.index(expected_symbol) + 1
            if expected_symbol and expected_symbol in symbols
            else None
        )
        rows.append(
            {
                **case,
                "file_rank": file_rank,
                "symbol_rank": symbol_rank,
                "top_paths": paths[:3],
                "latency_ms": round(latency_ms, 2),
            }
        )
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["library_id"]].append(row)
    summary = {}
    for library_id, items in grouped.items():
        summary[library_id] = {
            "cases": len(items),
            "file_hit@1": round(sum(1 for x in items if x["file_rank"] == 1) / len(items), 4),
            "file_hit@3": round(sum(1 for x in items if x["file_rank"] and x["file_rank"] <= 3) / len(items), 4),
            "symbol_hit@1": round(
                sum(1 for x in items if x["symbol_rank"] == 1)
                / max(1, sum(1 for x in items if str(x.get("expected_symbol") or ""))),
                4,
            )
            if any(str(x.get("expected_symbol") or "") for x in items)
            else None,
            "p95_latency_ms": round(sorted(x["latency_ms"] for x in items)[max(0, int(len(items) * 0.95) - 1)], 2),
        }
    output = {"summary": summary, "rows": rows}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
