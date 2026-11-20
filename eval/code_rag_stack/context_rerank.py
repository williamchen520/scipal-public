"""W3: BM25 top100 + query-aware repo-map prior, dev/holdout evaluation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from code_rag.bm25 import search_bm25
from code_rag.repomap import build_repomap


def load(case: dict) -> dict:
    hits = search_bm25(case["query"], library_id=case["library_id"], top_k=100)
    repomap = build_repomap(
        library_id=case["library_id"], query=case["query"], max_tokens=4000
    )
    prior = {item["path"]: float(item["score"]) for item in repomap.get("files", [])}
    return {"case": case, "hits": hits, "prior": prior, "top": max(prior.values(), default=0.0)}


def rank(item: dict, alpha: float) -> dict:
    case, hits, prior, top = item["case"], item["hits"], item["prior"], item["top"]
    ranked = []
    for hit in hits:
        value = float(hit.get("score") or 0.0)
        if top:
            value *= 1.0 + alpha * prior.get(hit.get("path"), 0.0) / top
        ranked.append((value, hit.get("path", "")))
    ranked.sort(reverse=True)
    paths = [path for _, path in ranked]
    expected = case["expected_path"]
    rank_no = next((i for i, path in enumerate(paths, 1) if path == expected), None)
    return {"file_rank": rank_no, "file_hit@1": rank_no == 1, "file_hit@3": bool(rank_no and rank_no <= 3)}

def evaluate(items: list[dict], alpha: float) -> dict:
    rows = [rank(item, alpha) for item in items]
    n = max(len(rows), 1)
    return {
        "alpha": alpha,
        "file_hit@1": round(sum(1 for row in rows if row["file_hit@1"]) / n, 4),
        "file_hit@3": round(sum(1 for row in rows if row["file_hit@3"]) / n, 4),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--alphas", default="0,0.1,0.25,0.5,1.0")
    parser.add_argument("--enabled", action="store_true")
    args = parser.parse_args()
    if not os.environ.get("SCIPAL_CODE_READ_DSN") and not os.environ.get("SCIPAL_CODE_DSN"):
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    alphas = [float(value) for value in args.alphas.split(",") if value]
    items = [load(case) for case in cases]
    results = [evaluate(items, alpha) for alpha in alphas]
    Path(args.output).write_text(
        json.dumps({"cases": len(cases), "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for result in results:
        print(result["alpha"], result["file_hit@1"], result["file_hit@3"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
