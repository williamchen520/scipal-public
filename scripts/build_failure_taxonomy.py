#!/usr/bin/env python3
"""Build a human labeling worksheet for S1 retrieval failures."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.retrieval_lab import rank_blend

FIELDS = [
    "question_id",
    "question",
    "query_type",
    "anchor_type",
    "anchor_type_source",
    "gold_cardinality",
    "failure_type",
    "baseline_ndcg",
    "fixed_ndcg",
    "delta_ndcg",
    "gold_rank_base",
    "gold_rank_fixed",
    "gold_in_pool",
    "gold_lexical_rank",
    "gold_paragraph_rank",
    "gold_rerank_score",
    "notes",
]


def _rank(ids: list[str], expected: set[str]) -> int:
    for index, sid in enumerate(ids, 1):
        if sid in expected:
            return index
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", default="artifacts/retrieval-traces-s1.jsonl")
    parser.add_argument("--questions", default="eval/s1_internal_questions.jsonl")
    parser.add_argument("--split", default="eval/s1_split.json")
    parser.add_argument("--out", default="artifacts/s1-failure-taxonomy.csv")
    args = parser.parse_args()
    questions = {
        row["question_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    split = set(json.loads(Path(args.split).read_text(encoding="utf-8"))["held_out"])
    traces = {
        row["query"]: row
        for row in (
            json.loads(line)
            for line in Path(args.trace).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    rows = []
    for question_id in sorted(split):
        question = questions.get(question_id)
        if not question:
            continue
        trace = traces.get(question["question"])
        if not trace:
            continue
        expected = set(question.get("gold_sentence_ids") or []) | set(question.get("acceptable_sentence_ids") or [])
        if not expected:
            continue
        base = rank_blend(trace, lam=0.0, mu=0.0, top_k=10)
        fixed = rank_blend(trace, lam=0.1, mu=0.0, top_k=10)
        pool = {row["sentence_id"]: row for row in trace.get("pool") or []}
        gold_row = next((pool[sid] for sid in expected if sid in pool), {})
        rows.append({
            "question_id": question_id,
            "question": question["question"],
            "query_type": "",
            "anchor_type": "",
            "anchor_type_source": "",
            "gold_cardinality": "single" if len(expected) == 1 else "multi",
            "failure_type": "",
            "baseline_ndcg": round(_ndcg(base, expected), 4),
            "fixed_ndcg": round(_ndcg(fixed, expected), 4),
            "delta_ndcg": round(_ndcg(fixed, expected) - _ndcg(base, expected), 4),
            "gold_rank_base": _rank(base, expected),
            "gold_rank_fixed": _rank(fixed, expected),
            "gold_in_pool": bool(gold_row),
            "gold_lexical_rank": gold_row.get("lexical_rank") or "",
            "gold_paragraph_rank": gold_row.get("paragraph_rank") or "",
            "gold_rerank_score": gold_row.get("rerank_score") or "",
            "notes": "",
        })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"rows={len(rows)} out={out}")
    return 0


def _ndcg(ids: list[str], expected: set[str]) -> float:
    import math

    gains = [1 if sid in expected else 0 for sid in ids]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = [1] * min(len(expected), len(ids))
    idcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
