"""Feedback regression gate: bm25_map must not lose to bm25."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_rag.bm25 import search_bm25
from code_rag.rerank import search_bm25_map


def file_rank(hits: list[dict], expected_path: str) -> int | None:
    for index, hit in enumerate(hits, 1):
        if hit.get("path") == expected_path:
            return index
    return None


def summarize(ranks: list[int | None]) -> dict:
    n = len(ranks)
    if not n:
        return {"cases": 0, "file@1": None, "file@3": None}
    return {
        "cases": n,
        "file@1": round(sum(1 for rank in ranks if rank == 1) / n, 4),
        "file@3": round(sum(1 for rank in ranks if rank and rank <= 3) / n, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="eval/code_rag_stack/feedback_cases.json")
    parser.add_argument("--output", default="eval/code_rag_stack/feedback_gate.json")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    usable = [case for case in cases if str(case.get("expected_path") or "").strip()]
    if not usable:
        result = {"status": "skip", "reason": "no feedback cases with expected_path", "cases": 0}
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("FEEDBACK_GATE_SKIP cases=0")
        return 0
    baseline_ranks = []
    candidate_ranks = []
    for case in usable:
        query = str(case["query"])
        library_id = str(case["library_id"])
        expected = str(case["expected_path"])
        baseline_ranks.append(
            file_rank(search_bm25(query, library_id=library_id, top_k=args.top_k), expected)
        )
        candidate_ranks.append(
            file_rank(search_bm25_map(query, library_id=library_id, top_k=args.top_k), expected)
        )
    baseline = summarize(baseline_ranks)
    candidate = summarize(candidate_ranks)
    passed = (candidate["file@1"] or 0) >= (baseline["file@1"] or 0)
    result = {
        "status": "pass" if passed else "fail",
        "baseline": baseline,
        "candidate": candidate,
        "rule": "candidate file@1 >= baseline file@1",
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
