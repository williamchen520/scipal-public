"""CoIR CodeSearchNet-python BM25 via Elasticsearch."""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

from datasets import load_dataset

INDEX = "coir_csn_python_bm25"


def request(method: str, path: str, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode("utf-8", "replace")) from error


def ndcg(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, doc in enumerate(ranked[:k], 1) if doc in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--es-url", default="http://127.0.0.1:9210")
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output", default="eval/code_rag_stack/coir_csn_python_es_1000.json")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args()
    random.seed(args.seed)
    qds = load_dataset("CoIR-Retrieval/CodeSearchNet-python-queries-corpus")
    qrels_ds = load_dataset("CoIR-Retrieval/CodeSearchNet-python-qrels")["test"]
    queries = {row["_id"]: row["text"] for row in qds["queries"]}
    corpus = {row["_id"]: row["text"] for row in qds["corpus"]}
    qrels: dict[str, set[str]] = {}
    for row in qrels_ds:
        qrels.setdefault(row["query_id"], set()).add(row["corpus_id"])
    query_ids = [qid for qid in qrels if qid in queries]
    random.shuffle(query_ids)
    query_ids = query_ids[: args.queries]
    started = time.perf_counter()
    try:
        request("DELETE", f"{args.es_url}/{INDEX}")
    except RuntimeError:
        pass
    request(
        "PUT",
        f"{args.es_url}/{INDEX}",
        {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {"properties": {"text": {"type": "text"}}},
        },
    )
    docs = list(corpus.items())
    for start in range(0, len(docs), 1000):
        batch = docs[start : start + 1000]
        lines = []
        for doc_id, text in batch:
            lines.append(json.dumps({"index": {"_id": doc_id}}))
            lines.append(json.dumps({"text": text}, ensure_ascii=False))
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        req = urllib.request.Request(
            f"{args.es_url}/{INDEX}/_bulk?refresh=false",
            data=payload,
            headers={"Content-Type": "application/x-ndjson"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
        if result.get("errors"):
            raise RuntimeError("bulk index errors")
    request("POST", f"{args.es_url}/{INDEX}/_refresh")
    load_seconds = time.perf_counter() - started
    metrics = {"ndcg@10": 0.0, "mrr@10": 0.0, "recall@100": 0.0}
    empty = 0
    qstarted = time.perf_counter()
    batch_size = max(1, int(args.batch))
    for start in range(0, len(query_ids), batch_size):
        batch = query_ids[start : start + batch_size]
        lines = []
        for qid in batch:
            lines.append(json.dumps({"index": INDEX}))
            lines.append(
                json.dumps(
                    {"query": {"match": {"text": queries[qid]}}, "size": 100, "_source": False},
                    ensure_ascii=False,
                )
            )
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        req = urllib.request.Request(
            f"{args.es_url}/_msearch",
            data=payload,
            headers={"Content-Type": "application/x-ndjson"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
        for qid, item in zip(batch, result.get("responses", [])):
            ranked = [hit["_id"] for hit in item.get("hits", {}).get("hits", [])]
            if not ranked:
                empty += 1
            rel = qrels[qid]
            metrics["ndcg@10"] += ndcg(ranked, rel, 10)
            rank = next((i for i, doc in enumerate(ranked[:10], 1) if doc in rel), None)
            metrics["mrr@10"] += 1.0 / rank if rank else 0.0
            metrics["recall@100"] += len(set(ranked[:100]) & rel) / max(len(rel), 1)
    query_seconds = time.perf_counter() - qstarted
    if not args.keep:
        request("DELETE", f"{args.es_url}/{INDEX}")
    count = max(len(query_ids), 1)
    result = {
        "dataset": "CoIR/CodeSearchNet-python",
        "engine": "Elasticsearch BM25",
        "subset": {"queries": len(query_ids), "corpus": len(corpus), "seed": args.seed},
        "metrics": {key: round(value / count, 4) for key, value in metrics.items()},
        "empty_queries": empty,
        "load_seconds": round(load_seconds, 1),
        "query_seconds": round(query_seconds, 1),
        "note": "full corpus, fixed query sample; not official leaderboard",
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
