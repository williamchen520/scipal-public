"""Small CoIR A/B: BM25 vs codeRAG, 1k corpus, 50 queries."""

from __future__ import annotations

import json
import math
import os
import random
import re
import time
from collections import Counter
from pathlib import Path

import psycopg
from datasets import load_dataset
from sentence_transformers import SentenceTransformer

from code_rag.index import index_library
from code_rag.search import search
from code_rag.symbols import normalize_symbol

LIB = "lib_coir_small"
SNAP = "snap_coir_small"
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")


def toks(text: str) -> list[str]:
    return [x.lower() for x in TOKEN.findall(text or "")]


def ndcg(ranked: list[str], rel: set[str], k: int = 10) -> float:
    dcg = sum(1 / math.log2(i + 1) for i, d in enumerate(ranked[:k], 1) if d in rel)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(len(rel), k) + 1))
    return dcg / ideal if ideal else 0.0


def one(ranked: list[str], rel: set[str]) -> tuple[float, float, float]:
    rank = next((i for i, d in enumerate(ranked[:10], 1) if d in rel), None)
    return ndcg(ranked, rel), 1 / rank if rank else 0.0, len(set(ranked[:100]) & rel) / max(len(rel), 1)


def main() -> int:
    random.seed(17)
    qds = load_dataset("CoIR-Retrieval/CodeSearchNet-python-queries-corpus")
    qrels_ds = load_dataset("CoIR-Retrieval/CodeSearchNet-python-qrels")["test"]
    queries = {r["_id"]: r["text"] for r in qds["queries"]}
    corpus = {r["_id"]: r["text"] for r in qds["corpus"]}
    qrels: dict[str, set[str]] = {}
    for r in qrels_ds:
        qrels.setdefault(r["query_id"], set()).add(r["corpus_id"])
    qids = [q for q in qrels if q in queries]
    random.shuffle(qids)
    qids = qids[:50]
    positives = {d for q in qids for d in qrels[q] if d in corpus}
    negs = [d for d in corpus if d not in positives]
    random.shuffle(negs)
    docs = [(d, corpus[d]) for d in positives | set(negs[: max(0, 1000 - len(positives))])]
    tokenized = [(d, Counter(toks(t))) for d, t in docs]
    df = Counter(term for _, tf in tokenized for term in tf)
    avg = sum(sum(tf.values()) for _, tf in tokenized) / len(tokenized)
    bm25 = []
    for q in qids:
        scores = Counter()
        for term in set(toks(queries[q])):
            for d, tf in tokenized:
                n = tf.get(term, 0)
                if n:
                    scores[d] += math.log(1 + (len(docs) - df[term] + .5) / (df[term] + .5))
        bm25.append(one([d for d, _ in scores.most_common(100)], qrels[q]))
    model = SentenceTransformer("G:/models/bge-small-zh-v1.5", device=os.environ.get("SCIPAL_CODE_DEVICE", "cpu"))
    dsn = os.environ["SCIPAL_CODE_DSN"]
    with psycopg.connect(dsn) as conn:
        for table in ("code_edges", "code_units", "code_files", "code_snapshots", "code_sources"):
            key = "src_unit_id" if table == "code_edges" else "library_id"
            conn.execute(f"DELETE FROM code_rag.{table} WHERE {key}='{LIB}'")
        conn.execute("INSERT INTO code_rag.code_sources (source_id,library_id,repo_url,ref,license) VALUES ('src_coir_small',%s,'bench','bench','Apache-2.0')", (LIB,))
        conn.execute("INSERT INTO code_rag.code_snapshots (snapshot_id,source_id,library_id,commit_sha,ref,is_active) VALUES (%s,'src_coir_small',%s,'small','bench',true)", (SNAP, LIB))
        for doc_id, text in docs:
            file_id, unit_id = f"file_{doc_id}", f"unit_{doc_id}"
            conn.execute("INSERT INTO code_rag.code_files (file_id,snapshot_id,library_id,path,language,content_hash) VALUES (%s,%s,%s,%s,'python','')", (file_id, SNAP, LIB, f"coir/{doc_id}.py"))
            conn.execute("INSERT INTO code_rag.code_units (unit_id,snapshot_id,library_id,file_id,symbol_name,unit_type,text,start_line,end_line) VALUES (%s,%s,%s,%s,%s,'function',%s,1,%s)", (unit_id, SNAP, LIB, file_id, doc_id, text, max(1, text.count("\n") + 1)))
            conn.execute("INSERT INTO code_rag.code_symbols (unit_id,library_id,snapshot_id,symbol_name,normalized_name,path,unit_type,start_line,end_line) VALUES (%s,%s,%s,%s,%s,%s,'function',1,%s)", (unit_id, LIB, SNAP, doc_id, normalize_symbol(doc_id), f"coir/{doc_id}.py", max(1, text.count("\n") + 1)))
        conn.commit()
    index_library(dsn, LIB, SNAP, model_name="G:/models/bge-small-zh-v1.5", device=model.device)
    rag = []
    for q in qids:
        hits = search(queries[q], library_id=LIB, snapshot_id=SNAP, top_k=100, model=model)
        rag.append(one([h["symbol_name"] for h in hits], qrels[q]))
    with psycopg.connect(dsn) as conn:
        for table in ("code_edges", "code_units", "code_files", "code_snapshots", "code_sources"):
            key = "src_unit_id" if table == "code_edges" else "library_id"
            conn.execute(f"DELETE FROM code_rag.{table} WHERE {key}='{LIB}'")
        conn.commit()
    result = {
        "dataset": "CoIR/CodeSearchNet-python-small",
        "queries": len(qids),
        "corpus": len(docs),
        "bm25": {k: round(sum(x[i] for x in bm25) / len(bm25), 4) for i, k in enumerate(("ndcg@10", "mrr@10", "recall@100"))},
        "code_rag": {k: round(sum(x[i] for x in rag) / len(rag), 4) for i, k in enumerate(("ndcg@10", "mrr@10", "recall@100"))},
    }
    Path("eval/code_rag_stack/coir_small_ab.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
