"""BM25 + query-aware repo-map prior rerank."""

from __future__ import annotations

from typing import Any

from code_rag.bm25 import search_bm25
from code_rag.repomap import build_repomap


def search_bm25_map(
    query: str,
    *,
    library_id: str,
    top_k: int = 10,
    snapshot_id: str = "",
    alpha: float = 1.0,
) -> list[dict[str, Any]]:
    hits = search_bm25(query, library_id=library_id, top_k=100, snapshot_id=snapshot_id)
    if not hits:
        return []
    repomap = build_repomap(
        library_id=library_id,
        snapshot_id=snapshot_id,
        query=query,
        max_tokens=4000,
    )
    prior = {item["path"]: float(item["score"]) for item in repomap.get("files", [])}
    top = max(prior.values(), default=0.0)
    ranked = []
    for hit in hits:
        value = float(hit.get("score") or 0.0)
        if top:
            value *= 1.0 + alpha * prior.get(hit.get("path"), 0.0) / top
        ranked.append((value, hit))
    ranked.sort(key=lambda item: item[0], reverse=True)
    result = []
    for value, hit in ranked[: max(1, min(int(top_k), 100))]:
        item = dict(hit)
        item["context_score"] = round(value, 6)
        result.append(item)
    return result
