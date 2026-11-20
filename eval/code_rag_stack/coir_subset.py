"""CoIR CodeSearchNet-python subset baseline with BM25.

This is a *subset* for engineering calibration, not the official full score.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import Counter
from pathlib import Path

from datasets import load_dataset

TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN.findall(text or "")]


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = 0.0
    for i, doc_id in enumerate(ranked[:k], 1):
        if doc_id in relevant:
            dcg += 1.0 / math.log2(i + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--corpus", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output", default="eval/code_rag_stack/coir_csn_python_subset.json")
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
    positives = {doc for qid in query_ids for doc in qrels[qid] if doc in corpus}
    candidates = [doc for doc in corpus if doc not in positives]
    random.shuffle(candidates)
    selected = positives | set(candidates[: max(0, args.corpus - len(positives))])
    docs = [(doc_id, corpus[doc_id]) for doc_id in selected]
    tokenized = [(doc_id, Counter(tokenize(text))) for doc_id, text in docs]
    lengths = {doc_id: sum(tf.values()) for doc_id, tf in tokenized}
    avg_len = sum(lengths.values()) / max(len(lengths), 1)
    df: Counter[str] = Counter()
    postings: dict[str, list[tuple[str, int]]] = {}
    for doc_id, tf in tokenized:
        for term, count in tf.items():
            df[term] += 1
            postings.setdefault(term, []).append((doc_id, count))
    n_docs = len(docs)
    k1, b = 1.5, 0.75
    metrics = {"ndcg@10": 0.0, "mrr@10": 0.0, "recall@100": 0.0}
    for qid in query_ids:
        terms = tokenize(queries[qid])
        scores: Counter[str] = Counter()
        for term in set(terms):
            post = postings.get(term, [])
            idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            for doc_id, tf in post:
                denom = tf + k1 * (1 - b + b * lengths[doc_id] / max(avg_len, 1))
                scores[doc_id] += idf * tf * (k1 + 1) / denom
        ranked = [doc for doc, _ in scores.most_common(100)]
        rel = qrels[qid]
        metrics["ndcg@10"] += ndcg_at_k(ranked, rel, 10)
        rank = next((i for i, doc in enumerate(ranked[:10], 1) if doc in rel), None)
        metrics["mrr@10"] += 1.0 / rank if rank else 0.0
        metrics["recall@100"] += len(set(ranked[:100]) & rel) / max(len(rel), 1)
    count = max(len(query_ids), 1)
    result = {
        "dataset": "CoIR/CodeSearchNet-python",
        "subset": {"queries": len(query_ids), "corpus": n_docs, "seed": args.seed},
        "baseline": "BM25 (k1=1.5,b=0.75)",
        "metrics": {key: round(value / count, 4) for key, value in metrics.items()},
        "note": "subset only; not official full CoIR score",
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
