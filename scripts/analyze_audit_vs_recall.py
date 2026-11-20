#!/usr/bin/env python3
"""E1: compare recall with audit facet status on existing S1 traces."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.retrieval_lab import rank_blend
from services.audit.retrieval_audit import build_audit_record


def _ndcg(ids: list[str], expected: set[str]) -> float:
    gains = [1 if sid in expected else 0 for sid in ids]
    dcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = [1] * min(len(expected), len(ids))
    idcg = sum(gain / math.log2(index + 2) for index, gain in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", default="artifacts/retrieval-traces-s1.jsonl")
    parser.add_argument("--questions", default="eval/s1_internal_questions.jsonl")
    parser.add_argument("--split", default="eval/s1_split.json")
    args = parser.parse_args()
    questions = {
        row["question_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    split = json.loads(Path(args.split).read_text(encoding="utf-8"))
    split_of = {qid: "dev" for qid in split["dev"]}
    split_of.update({qid: "held_out" for qid in split["held_out"]})
    traces = {
        row["query"]: row
        for row in (
            json.loads(line)
            for line in Path(args.trace).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    rows = []
    for qid, question in questions.items():
        trace = traces.get(question["question"])
        if not trace:
            continue
        expected = set(question.get("gold_sentence_ids") or []) | set(question.get("acceptable_sentence_ids") or [])
        if not expected:
            continue
        ranked = rank_blend(trace, top_k=10)
        recall = len(set(ranked) & expected) / len(expected)
        bundle = {
            "evidence": [
                {
                    "paper_id": row.get("paper_id"),
                    "para_id": row.get("para_id"),
                    "highlight": [{
                        "sentence_id": row.get("sentence_id"),
                        "text": row.get("text") or "",
                    }],
                }
                for row in (trace.get("final") or [])[:10]
            ]
        }
        audit = build_audit_record(query=question["question"], bundle=bundle)
        rows.append({
            "question_id": qid,
            "split": split_of.get(qid, "unknown"),
            "recall@10": round(recall, 4),
            "ndcg@10": round(_ndcg(ranked, expected), 4),
            "facet_status": audit["coverage"]["facet_status"],
            "facet_missing": audit["coverage"]["missing_facet_count"],
            "high_recall": recall >= 0.8,
        })
    summary = {
        "queries": len(rows),
        "mean_recall": round(sum(row["recall@10"] for row in rows) / len(rows), 4) if rows else None,
        "mean_ndcg": round(sum(row["ndcg@10"] for row in rows) / len(rows), 4) if rows else None,
        "facet_covered": sum(1 for row in rows if row["facet_status"] == "covered"),
        "facet_partial": sum(1 for row in rows if row["facet_status"] == "partial"),
        "facet_uncovered": sum(1 for row in rows if row["facet_status"] == "uncovered"),
        "high_recall_but_partial": sum(
            1 for row in rows if row["high_recall"] and row["facet_status"] != "covered"
        ),
        "by_split": {
            key: {
                "queries": sum(1 for row in rows if row["split"] == key),
                "mean_recall": round(
                    sum(row["recall@10"] for row in rows if row["split"] == key)
                    / max(1, sum(1 for row in rows if row["split"] == key)), 4
                ),
            }
            for key in ("dev", "held_out")
        },
    }
    print(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
