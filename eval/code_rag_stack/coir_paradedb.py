"""CoIR CodeSearchNet-python BM25 via ParadeDB pg_search."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import time
from pathlib import Path

import psycopg
from datasets import load_dataset

TABLE = "public.coir_csn_python_bm25"
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


def ndcg(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, doc in enumerate(ranked[:k], 1) if doc in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PARADEDB_DSN", ""))
    parser.add_argument("--queries", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output", default="eval/code_rag_stack/coir_csn_python_paradedb_1000.json")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=5000)
    parser.add_argument("--term-cap", type=int, default=64)
    parser.add_argument("--slow-log", default="")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PARADEDB_DSN is required")
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
    with psycopg.connect(args.dsn) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.execute(f"CREATE TABLE {TABLE} (doc_id text PRIMARY KEY, text text NOT NULL)")
        with conn.cursor().copy(f"COPY {TABLE} (doc_id, text) FROM STDIN") as copy:
            for doc_id, text in corpus.items():
                copy.write_row((doc_id, text))
        conn.execute(
            f"CREATE INDEX coir_csn_python_bm25_idx ON {TABLE} "
            "USING bm25 (doc_id, text) WITH (key_field='doc_id')"
        )
        conn.commit()
        load_seconds = time.perf_counter() - started
        conn.execute(f"SET statement_timeout = {max(1, int(args.timeout_ms))}")
        metrics = {"ndcg@10": 0.0, "mrr@10": 0.0, "recall@100": 0.0}
        empty = 0
        timeouts = 0
        slow = []
        qstarted = time.perf_counter()
        for qid in query_ids:
            raw = queries[qid][:1000]
            terms = list(dict.fromkeys(TOKEN.findall(raw)))
            text = " ".join(terms[: max(1, int(args.term_cap))])
            t0 = time.perf_counter()
            try:
                rows = conn.execute(
                    f"SELECT doc_id FROM {TABLE} WHERE text @@@ pdb.match(%s, NULL, 0, false, false, false) "
                    "ORDER BY pdb.score(doc_id) DESC LIMIT 100",
                    (text,),
                ).fetchall()
            except psycopg.errors.QueryCanceled:
                conn.rollback()
                timeouts += 1
                continue
            elapsed = time.perf_counter() - t0
            if elapsed > 1.0:
                slow.append({"query_id": qid, "chars": len(raw), "terms": len(terms), "seconds": round(elapsed, 3)})
            ranked = [row[0] for row in rows]
            if not ranked:
                empty += 1
            rel = qrels[qid]
            metrics["ndcg@10"] += ndcg(ranked, rel, 10)
            rank = next((i for i, doc in enumerate(ranked[:10], 1) if doc in rel), None)
            metrics["mrr@10"] += 1.0 / rank if rank else 0.0
            metrics["recall@100"] += len(set(ranked[:100]) & rel) / max(len(rel), 1)
        query_seconds = time.perf_counter() - qstarted
        if not args.keep:
            conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
            conn.commit()
    count = max(len(query_ids), 1)
    result = {
        "dataset": "CoIR/CodeSearchNet-python",
        "engine": "ParadeDB pg_search BM25",
        "subset": {"queries": len(query_ids), "corpus": len(corpus), "seed": args.seed},
        "metrics": {key: round(value / count, 4) for key, value in metrics.items()},
        "empty_queries": empty,
        "timeouts": timeouts,
        "slow_queries": sorted(slow, key=lambda item: item["seconds"], reverse=True)[:20],
        "load_seconds": round(load_seconds, 1),
        "query_seconds": round(query_seconds, 1),
        "note": "full corpus, fixed query sample; not official leaderboard",
    }
    if args.slow_log:
        Path(args.slow_log).write_text(json.dumps(result.get("slow_queries", []), ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
