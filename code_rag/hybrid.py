"""Hybrid BM25 + codeRAG retrieval with reciprocal rank fusion."""

from __future__ import annotations

import os
from typing import Any

from code_rag.bm25 import search_bm25
from code_rag.search import search


def search_hybrid(
    query: str,
    *,
    library_id: str,
    top_k: int = 10,
    snapshot_id: str = "",
    bm25_weight: float = 1.0,
    rag_weight: float = 1.0,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(top_k), 100))
    bm25_hits = search_bm25(
        query, library_id=library_id, top_k=50, snapshot_id=snapshot_id
    )
    try:
        rag_hits = search(
            query, library_id=library_id, top_k=50, snapshot_id=snapshot_id
        )
    except Exception:
        rag_hits = []
    scores: dict[str, float] = {}
    payload: dict[str, dict[str, Any]] = {}
    sources: dict[str, list[str]] = {}
    for weight, hits, name in (
        (bm25_weight, bm25_hits, "bm25"),
        (rag_weight, rag_hits, "coderag"),
    ):
        for rank, hit in enumerate(hits, 1):
            unit_id = hit["unit_id"]
            scores[unit_id] = scores.get(unit_id, 0.0) + weight / (60 + rank)
            payload.setdefault(unit_id, hit)
            sources.setdefault(unit_id, []).append(name)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    result = []
    for unit_id, score in ordered:
        item = dict(payload[unit_id])
        item["hybrid_score"] = round(score, 6)
        item["sources"] = sources[unit_id]
        result.append(item)
    return result
