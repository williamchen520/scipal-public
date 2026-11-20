#!/usr/bin/env python3
"""Offline replay, parity and bounded post-rerank parameter sweep."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

DEFAULT_GRID = (0.0, 0.02, 0.05, 0.1)


def _norm(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high <= low:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def rank_blend(trace: dict[str, Any], *, lam: float = 0.0, mu: float = 0.0, top_k: int | None = None) -> list[str]:
    pool = [
        row for row in trace.get("pool") or []
        if row.get("rerank_score") is not None
    ]
    lexical = _norm([float(row.get("lexical_score") or 0.0) for row in pool])
    prior = _norm([float(row.get("paragraph_prior") or 0.0) for row in pool])
    scored = []
    for index, row in enumerate(pool):
        score = float(row["rerank_score"]) + lam * lexical[index] + mu * prior[index]
        scored.append((score, index, row["sentence_id"]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    limit = top_k if top_k is not None else int((trace.get("config") or {}).get("top_k") or 0)
    if limit <= 0:
        limit = len(scored)
    return [sentence_id for _, _, sentence_id in scored[:limit]]


def replay(trace: dict[str, Any]) -> list[str]:
    return rank_blend(trace)


def parity(trace: dict[str, Any]) -> dict[str, Any]:
    expected = [row.get("sentence_id") for row in trace.get("final") or []]
    actual = rank_blend(trace)
    return {
        "trace_id": trace.get("trace_id"),
        "ok": actual == expected,
        "expected": expected,
        "actual": actual,
    }


def _dcg(gains: list[int]) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))


def evaluate(
    traces: list[dict[str, Any]],
    gold: dict[str, set[str]],
    *,
    lam: float,
    mu: float,
    top_k: int = 10,
) -> dict[str, Any]:
    recalls, mrrs, ndcgs = [], [], []
    matched = 0
    overlap_queries = 0
    for trace in traces:
        expected = gold.get(trace.get("query") or "")
        if not expected:
            continue
        matched += 1
        pool_ids = {row.get("sentence_id") for row in trace.get("pool") or []}
        if pool_ids & expected:
            overlap_queries += 1
        ranked = rank_blend(trace, lam=lam, mu=mu, top_k=top_k)
        hits = set(ranked) & expected
        recalls.append(len(hits) / len(expected))
        first = next((index for index, sid in enumerate(ranked) if sid in expected), None)
        mrrs.append(1.0 / (first + 1) if first is not None else 0.0)
        gains = [1 if sid in expected else 0 for sid in ranked]
        ideal = [1] * min(len(expected), top_k)
        ndcgs.append(_dcg(gains) / _dcg(ideal) if _dcg(ideal) else 0.0)
    count = len(recalls)
    return {
        "queries": matched,
        "recall@10": round(sum(recalls) / count, 4) if count else None,
        "mrr": round(sum(mrrs) / count, 4) if count else None,
        "ndcg@10": round(sum(ndcgs) / count, 4) if count else None,
        "aligned": overlap_queries > 0,
        "queries_with_id_overlap": overlap_queries,
        "lambda": lam,
        "mu": mu,
    }


def per_query(
    traces: list[dict[str, Any]],
    gold: dict[str, set[str]],
    *,
    lam: float,
    mu: float,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    rows = []
    for trace in traces:
        expected = gold.get(trace.get("query") or "")
        if not expected:
            continue
        ranked = rank_blend(trace, lam=lam, mu=mu, top_k=top_k)
        hits = set(ranked) & expected
        first = next((index for index, sid in enumerate(ranked) if sid in expected), None)
        gains = [1 if sid in expected else 0 for sid in ranked]
        ideal = [1] * min(len(expected), top_k)
        rows.append({
            "query": trace.get("query"),
            "recall@10": len(hits) / len(expected),
            "mrr": 1.0 / (first + 1) if first is not None else 0.0,
            "ndcg@10": _dcg(gains) / _dcg(ideal) if _dcg(ideal) else 0.0,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", default="logs/retrieval-traces.jsonl")
    parser.add_argument("--gold", default="eval/gold/seed_100.jsonl")
    parser.add_argument("--split", choices=("val", "test", "dev", "held_out", "all"), default="val")
    parser.add_argument("--split-file", default="")
    parser.add_argument("--parity", action="store_true")
    parser.add_argument("--fixed-lambda", type=float, default=None)
    parser.add_argument("--fixed-mu", type=float, default=0.0)
    parser.add_argument("--bootstrap", type=int, default=0)
    args = parser.parse_args()
    traces = [
        json.loads(line)
        for line in Path(args.trace).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    gold_rows = [
        json.loads(line)
        for line in Path(args.gold).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    gold = {}
    id_by_question = {}
    for row in gold_rows:
        evidence = set(row.get("evidence") or []) | set(row.get("gold_sentence_ids") or []) | set(row.get("acceptable_sentence_ids") or [])
        gold[row["question"]] = evidence
        id_by_question[row["question"]] = row.get("id") or row.get("question_id") or ""
    matched = [trace for trace in traces if trace.get("query") in gold]
    if args.parity:
        results = [parity(trace) for trace in matched]
        summary = {
            "traces": len(results),
            "parity_ok": sum(1 for row in results if row["ok"]),
            "parity_rate": round(sum(1 for row in results if row["ok"]) / len(results), 4) if results else None,
        }
        print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
        return 0 if all(row["ok"] for row in results) else 1
    if args.split_file:
        split = json.loads(Path(args.split_file).read_text(encoding="utf-8"))
        if args.split in {"dev", "held_out"}:
            keep = set(split.get(args.split) or [])
            selected = [trace for trace in matched if id_by_question.get(trace.get("query")) in keep]
        else:
            selected = matched
    else:
        cutoff = max(1, int(len(matched) * 0.7))
        if args.split == "val":
            selected = matched[:cutoff]
        elif args.split == "test":
            selected = matched[cutoff:]
        else:
            selected = matched
    baseline = evaluate(selected, gold, lam=0.0, mu=0.0)
    if args.fixed_lambda is not None:
        fixed = evaluate(selected, gold, lam=args.fixed_lambda, mu=args.fixed_mu)
        base_rows = per_query(selected, gold, lam=0.0, mu=0.0)
        fixed_rows = per_query(selected, gold, lam=args.fixed_lambda, mu=args.fixed_mu)
        result = {
            "split": args.split,
            "selected_queries": len(selected),
            "baseline": baseline,
            "fixed": fixed,
            "per_query": [
                {
                    "query": a["query"],
                    "baseline_ndcg": round(a["ndcg@10"], 4),
                    "fixed_ndcg": round(b["ndcg@10"], 4),
                    "delta_ndcg": round(b["ndcg@10"] - a["ndcg@10"], 4),
                }
                for a, b in zip(base_rows, fixed_rows)
            ],
        }
        if args.bootstrap > 0:
            deltas = [b["ndcg@10"] - a["ndcg@10"] for a, b in zip(base_rows, fixed_rows)]
            rng = random.Random(42)
            samples = []
            for _ in range(args.bootstrap):
                draw = [rng.choice(deltas) for _ in deltas]
                samples.append(sum(draw) / len(draw))
            samples.sort()
            lo = samples[int(0.025 * len(samples))]
            hi = samples[int(0.975 * len(samples)) - 1]
            result["bootstrap"] = {
                "metric": "ndcg@10",
                "mean_delta": round(sum(deltas) / len(deltas), 4),
                "ci95": [round(lo, 4), round(hi, 4)],
                "positive_rate": round(sum(1 for d in deltas if d > 0) / len(deltas), 4),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if not baseline.get("aligned"):
        print(json.dumps({
            "split": args.split,
            "selected_queries": len(selected),
            "baseline": baseline,
            "error": "gold/trace evidence IDs do not overlap; refusing to report metrics",
        }, ensure_ascii=False, indent=2))
        return 1
    grid = []
    for lam in DEFAULT_GRID:
        for mu in DEFAULT_GRID:
            if lam == 0.0 and mu == 0.0:
                continue
            grid.append(evaluate(selected, gold, lam=lam, mu=mu))
    grid.sort(key=lambda row: (-(row["ndcg@10"] or 0), row["lambda"], row["mu"]))
    print(json.dumps({
        "split": args.split,
        "selected_queries": len(selected),
        "baseline": baseline,
        "best": grid[0] if grid else None,
        "top5": grid[:5],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
