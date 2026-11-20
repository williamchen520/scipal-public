"""S2.3d: paper candidates with separate base/paper reranking."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from services.search.paper_vector import PaperVectorSearch
from services.search.sentence_hybrid import (
    SentenceHybridRetriever,
    _ts_query,
    units_to_evidence_json,
)
from services.search.sentence_window import build_context


class PaperQuotaRetriever:
    """Keep base ranking intact; add a small, separately-reranked paper quota."""

    def __init__(
        self,
        *,
        base: Optional[SentenceHybridRetriever] = None,
        quota: Optional[int] = None,
        paper_pool: int = 20,
        paragraphs_per_paper: int = 3,
        sentences_per_paper: int = 5,
    ) -> None:
        self.base = base or SentenceHybridRetriever()
        self.quota = max(0, int(quota if quota is not None else os.environ.get("SCIPAL_PAPER_QUOTA", "2")))
        self.paper_pool = max(1, int(paper_pool))
        self.paragraphs_per_paper = max(1, int(paragraphs_per_paper))
        self.sentences_per_paper = max(1, int(sentences_per_paper))
        self.paper_vector = PaperVectorSearch()

    def _pg(self):
        from services.db.pg_pool import corpus_connection

        return corpus_connection()

    def _fts_papers(self, query: str, limit: int) -> List[str]:
        ts_query = _ts_query(query)
        if not ts_query:
            return []
        pg = self._pg()
        try:
            rows = pg.execute(
                "SELECT paper_id FROM papers WHERE search_vector @@ to_tsquery('english', %s) "
                "AND duplicate_of IS NULL ORDER BY ts_rank(search_vector, "
                "to_tsquery('english', %s)) DESC LIMIT %s",
                (ts_query, ts_query, limit),
            ).fetchall()
        finally:
            pg.close()
        return [row["paper_id"] for row in rows]

    def _paper_sentences(self, pg, paper_id: str, query: str, limit: int) -> List[Dict[str, Any]]:
        ts_query = _ts_query(query)
        if not ts_query:
            return []
        rows = pg.execute(
            "SELECT s.sentence_id, s.para_id, s.paper_id, s.text, "
            "ts_rank(s.search_vector, to_tsquery('english', %s)) AS rank "
            "FROM sentences s WHERE s.paper_id=%s "
            "AND s.search_vector @@ to_tsquery('english', %s) "
            "ORDER BY rank DESC, s.sentence_id LIMIT %s",
            (ts_query, paper_id, ts_query, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _paper_units(
        self, query: str, query_embedding, base_paper_ids: set[str], top_n: int
    ) -> List[Dict[str, Any]]:
        candidate_ids: List[str] = []
        for row in self.paper_vector.search(query_embedding, top_k=50):
            candidate_ids.append(row["paper_id"])
        candidate_ids.extend(self._fts_papers(query, 20))
        candidate_ids = list(dict.fromkeys(candidate_ids))
        candidate_ids = [
            paper_id
            for paper_id in candidate_ids
            if paper_id and paper_id not in base_paper_ids
        ][: self.paper_pool]

        anchors: List[Dict[str, Any]] = []
        pg = self._pg()
        try:
            for paper_id in candidate_ids:
                rows = self._paper_sentences(
                    pg, paper_id, query, self.sentences_per_paper
                )
                if not rows:
                    # fallback: paragraph vector inside the candidate paper
                    hits = self.base.vector.search(
                        query_embedding,
                        top_k=self.paragraphs_per_paper,
                        paper_id=paper_id,
                    )
                    para_ids = [hit.para_id for hit in hits]
                    grouped = self.base._sentences_for_paragraphs(pg, para_ids)
                    for hit in hits:
                        for row in (grouped.get(hit.para_id) or [])[:3]:
                            anchors.append(
                                {
                                    "sentence_id": row["sentence_id"],
                                    "para_id": row["para_id"],
                                    "paper_id": row["paper_id"],
                                    "text": row.get("text") or "",
                                    "score": hit.rank,
                                }
                            )
                else:
                    for row in rows:
                        anchors.append(
                            {
                                "sentence_id": row["sentence_id"],
                                "para_id": row["para_id"],
                                "paper_id": row["paper_id"],
                                "text": row.get("text") or "",
                                "score": row.get("rank") or 0.0,
                            }
                        )
        finally:
            pg.close()

        if not anchors:
            return []
        reranked = self.base.reranker.rerank(
            query,
            [{"sentence_id": a["sentence_id"], "text": a["text"][:800]} for a in anchors],
            top_k=top_n,
            batch_size=16,
        )
        by_id = {anchor["sentence_id"]: anchor for anchor in anchors}
        out = []
        pg = self._pg()
        try:
            context = self.base._sentences_for_paragraphs(
                pg, [item["sentence_id"] and by_id[item["sentence_id"]]["para_id"] for item in reranked]
            )
        finally:
            pg.close()
        for item in reranked:
            anchor = by_id.get(item["sentence_id"])
            if not anchor:
                continue
            anchor = {**anchor, "score": item.get("rerank_score")}
            unit = build_context(
                anchor,
                context.get(anchor["para_id"], []),
                query=query,
                policy=self.base.context_policy,
            ).as_dict()
            out.append(unit)
        return out

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        base_units = self.base.search(query, top_k=top_k + self.quota)
        if not base_units or self.quota <= 0:
            return base_units[:top_k]
        base_paper_ids = {unit.get("paper_id") for unit in base_units}
        query_embedding = self.base.model.encode([query], normalize_embeddings=True)[0]
        paper_units = self._paper_units(
            query, query_embedding, base_paper_ids, self.quota
        )
        if not paper_units:
            return base_units[:top_k]
        return self.merge(base_units, paper_units, top_k=top_k, quota=self.quota)

    @staticmethod
    def merge(
        base_units: List[Dict[str, Any]],
        paper_units: List[Dict[str, Any]],
        *,
        top_k: int,
        quota: int,
    ) -> List[Dict[str, Any]]:
        if not paper_units:
            return base_units[:top_k]
        keep_base = max(1, top_k - quota)
        insert_at = min(8, len(base_units[:keep_base]))
        merged = (
            base_units[:insert_at]
            + paper_units[:quota]
            + base_units[insert_at:keep_base]
        )
        return merged[:top_k]

    def to_evidence_json(self, query: str, paper_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        top_k = int(kwargs.get("top_paragraphs") or kwargs.get("top_k") or 10)
        units = self.search(query, top_k=top_k)
        if paper_id:
            units = [unit for unit in units if unit.get("paper_id") == paper_id]
        return units_to_evidence_json(query, units)

    def search_hits(self, query: str, top_k: int = 10):
        from services.search.result import result_from_sentence_units

        return result_from_sentence_units(
            query, self.search(query, top_k=top_k), source="paper_quota"
        )
