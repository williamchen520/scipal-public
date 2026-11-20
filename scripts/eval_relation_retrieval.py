#!/usr/bin/env python3
"""Held-out citation link prediction for the relation ranker."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.relation_retrieval import adjacency, rank_from_adjacency


def load_edges(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        rows.append((item["citing_id"], item["cited_id"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edges", default="artifacts/relation-edges.jsonl")
    parser.add_argument("--papers", type=int, default=200)
    parser.add_argument("--negatives", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    edges = load_edges(Path(args.edges))
    by_citing: dict[str, list[str]] = defaultdict(list)
    all_cited = set()
    for citing, cited in edges:
        if cited not in by_citing[citing]:
            by_citing[citing].append(cited)
        all_cited.add(cited)
    outgoing, incoming = adjacency(edges)
    rng = random.Random(args.seed)
    recalls, reciprocal_ranks = [], []
    evaluated = 0
    for seed, refs in by_citing.items():
        if evaluated >= args.papers:
            break
        if len(refs) < 5:
            continue
        held = refs[-1]
        observed = set(refs[:-1])
        pool = sorted(all_cited - observed - {held})
        negatives = rng.sample(pool, max(0, min(args.negatives, len(pool))))
        candidates = observed | {held} | set(negatives)
        outgoing.get(seed, set()).discard(held)
        incoming.get(held, set()).discard(seed)
        ranked = rank_from_adjacency(seed, outgoing, incoming, limit=len(candidates), candidates=candidates)
        outgoing.get(seed, set()).add(held)
        incoming.get(held, set()).add(seed)
        ids = [row["paper_id"] for row in ranked]
        if held not in ids:
            continue
        rank = ids.index(held) + 1
        recalls.append(1.0 if rank <= 10 else 0.0)
        reciprocal_ranks.append(1.0 / rank)
        evaluated += 1
    result = {
        "edges": len(edges),
        "papers_evaluated": evaluated,
        "recall_at_10": round(sum(recalls) / len(recalls), 4) if recalls else None,
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else None,
        "negatives_per_query": args.negatives,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
