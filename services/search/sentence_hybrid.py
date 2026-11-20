"""Sentence-hybrid retrieval prototype.

Paragraph vectors provide a semantic prior; sentence lexical search provides
the actual ranking unit. Context is attached after ranking and is never scored.
"""

from __future__ import annotations

import os
import re
import time
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

from config.paths import EMBEDDING_MODEL
from services.search.pg_vector import PGVectorParagraphSearch
from services.search.reranker import Reranker
from services.search.sentence_window import WindowPolicy, build_context

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _ts_query(query: str) -> str:
    terms = [term for term in TOKEN_RE.findall(query or "") if len(term) > 1]
    return " | ".join(terms)


def units_to_evidence_json(query: str, units: List[Dict[str, Any]]) -> Dict[str, Any]:
    evidence = []
    for unit in units:
        sentence_id = unit.get("sentence_id")
        anchor_text = unit.get("anchor_text") or ""
        evidence.append(
            {
                "paper_id": unit.get("paper_id"),
                "para_id": unit.get("para_id"),
                "section_path": [],
                "text": unit.get("text") or anchor_text,
                "highlight": [
                    {
                        "sentence_id": sentence_id,
                        "text": anchor_text,
                        "score": unit.get("anchor_score"),
                    }
                ],
                "matched_sentences": [
                    {"sentence_id": sentence_id, "text": anchor_text}
                ],
                "paragraph_details": [
                    {
                        "para_id": unit.get("para_id"),
                        "sentence_ids": [
                            row.get("sentence_id")
                            for row in unit.get("window_sentences") or []
                            if row.get("sentence_id")
                        ],
                        "text": unit.get("paragraph_text") or "",
                    }
                ],
            }
        )
    return {
        "query": query,
        "evidence": evidence,
        "sufficient": bool(evidence),
        "sufficiency": {"sufficient": bool(evidence), "reason": "sentence_backend"},
        "summaries": [],
    }


class SentenceHybridRetriever:
    def __init__(
        self,
        *,
        model=None,
        vector: Optional[PGVectorParagraphSearch] = None,
        reranker=None,
        paragraph_top_k: int = 50,
        sentence_top_k: int = 200,
        rerank_pool: int = 50,
        lexical_weight: float = 0.7,
        paragraph_weight: float = 0.3,
        context_policy: Optional[WindowPolicy] = None,
        expand_queries: Optional[bool] = None,
        max_query_variants: int = 3,
        section_routing: Optional[bool] = None,
        section_boost: float = 0.0015,
        paper_candidates: Optional[bool] = None,
        paper_candidates_top_k: int = 20,
        paper_paragraphs_per_paper: int = 3,
        paper_vector: Optional[bool] = None,
        paper_vector_top_k: int = 8,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = model or SentenceTransformer(
            os.environ.get("SCIPAL_EMBEDDING_MODEL", EMBEDDING_MODEL)
        )
        self.vector = vector or PGVectorParagraphSearch()
        self.reranker = reranker or Reranker()
        self.paragraph_top_k = paragraph_top_k
        self.sentence_top_k = sentence_top_k
        self.rerank_pool = rerank_pool
        self.lexical_weight = lexical_weight
        self.paragraph_weight = paragraph_weight
        self.context_policy = context_policy or WindowPolicy.from_config()
        if expand_queries is None:
            expand_queries = os.environ.get(
                "SCIPAL_SENTENCE_EXPANSION", "0"
            ).strip().lower() in {"1", "true", "on", "yes"}
        self.expand_queries = bool(expand_queries)
        self.max_query_variants = max(1, int(max_query_variants))
        self.query_expander = None
        if section_routing is None:
            section_routing = os.environ.get(
                "SCIPAL_SECTION_ROUTING", "0"
            ).strip().lower() in {"1", "true", "on", "yes"}
        self.section_routing = bool(section_routing)
        self.section_boost = float(section_boost)
        if paper_candidates is None:
            paper_candidates = os.environ.get(
                "SCIPAL_PAPER_CANDIDATES", "0"
            ).strip().lower() in {"1", "true", "on", "yes"}
        self.paper_candidates = bool(paper_candidates)
        self.paper_candidates_top_k = max(1, int(paper_candidates_top_k))
        self.paper_paragraphs_per_paper = max(1, int(paper_paragraphs_per_paper))
        if paper_vector is None:
            paper_vector = os.environ.get(
                "SCIPAL_PAPER_VECTOR", "0"
            ).strip().lower() in {"1", "true", "on", "yes"}
        self.paper_vector = bool(paper_vector)
        self.paper_vector_top_k = max(1, int(paper_vector_top_k))
        self.paper_vector_search = None
        if self.paper_vector:
            from services.search.paper_vector import PaperVectorSearch

            self.paper_vector_search = PaperVectorSearch()
        if self.expand_queries:
            from services.search.query_expander import QueryExpander

            self.query_expander = QueryExpander(max_variants=self.max_query_variants)

    def _query_variants(self, query: str) -> List[str]:
        if not self.expand_queries or self.query_expander is None:
            return [query]
        try:
            variants = self.query_expander.expand(query)
        except Exception:
            return [query]
        out = [query]
        for variant in variants:
            variant = (variant or "").strip()
            if variant and variant not in out:
                out.append(variant)
            if len(out) >= self.max_query_variants:
                break
        return out

    @staticmethod
    def _route_terms(query: str) -> List[str]:
        q = (query or "").lower()
        dataset_cues = (
            "dataset", "data ", "sample", "cohort", "participant", "patient",
            "mouse model", "cell line", "serum panel", "trial", "assay",
        )
        limitation_cues = (
            "limitation", "conflict", "contradict", "concern", "difficult",
            "risk", "safety", "why ", "unclear", "discrepan",
        )
        method_cues = (
            "method", "statistical", "workflow", "staining", "culture",
            "immunoblot", "microscopy",
        )
        if any(cue in q for cue in limitation_cues):
            return ["discussion", "limitation", "conclusion"]
        if any(cue in q for cue in dataset_cues):
            return ["method", "materials", "data", "participant", "patient", "sample"]
        if any(cue in q for cue in method_cues):
            return ["method", "materials"]
        return []

    @staticmethod
    def _paper_candidates(pg, query: str, limit: int) -> List[str]:
        ts_query = _ts_query(query)
        if not ts_query:
            return []
        rows = pg.execute(
            "SELECT paper_id, ts_rank(search_vector, plainto_tsquery('english', %s)) AS rank "
            "FROM papers WHERE search_vector @@ plainto_tsquery('english', %s) "
            "AND duplicate_of IS NULL ORDER BY rank DESC, paper_id LIMIT %s",
            (query, query, limit),
        ).fetchall()
        return [row["paper_id"] for row in rows]

    @staticmethod
    def _paragraphs_for_paper(
        pg, paper_id: str, query: str, limit: int
    ) -> List[str]:
        ts_query = _ts_query(query)
        if not ts_query:
            return []
        rows = pg.execute(
            "SELECT para_id, ts_rank(search_vector, plainto_tsquery('english', %s)) AS rank "
            "FROM paragraphs WHERE paper_id=%s "
            "AND search_vector @@ plainto_tsquery('english', %s) "
            "ORDER BY rank DESC, para_id LIMIT %s",
            (query, paper_id, query, limit),
        ).fetchall()
        return [row["para_id"] for row in rows]

    def _pg(self):
        from services.db.pg_pool import corpus_connection

        return corpus_connection()

    @staticmethod
    def _lexical_rows(
        pg, query: str, limit: int, section_terms: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        ts_query = _ts_query(query)
        if not ts_query:
            return []
        where = "s.search_vector @@ to_tsquery('english', %s)"
        params: List[Any] = [ts_query]
        if section_terms:
            clause = " OR ".join(
                "(p.section_level1 ILIKE %s OR p.section_level2 ILIKE %s)"
                for _ in section_terms
            )
            where += f" AND ({clause})"
            for term in section_terms:
                params.extend([f"%{term}%", f"%{term}%"])
        params.append(limit)
        rows = pg.execute(
            "SELECT s.sentence_id, s.para_id, s.paper_id, s.text, s.sequence, "
            "p.section_level1 AS section_l1, p.section_level2 AS section_l2, "
            "ts_rank(s.search_vector, to_tsquery('english', %s)) AS rank "
            "FROM sentences s JOIN paragraphs p ON p.para_id=s.para_id "
            f"WHERE {where} "
            "ORDER BY rank DESC, s.sentence_id LIMIT %s",
            (ts_query, *params),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _sentences_for_paragraphs(
        pg, para_ids: Iterable[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        ids = list(dict.fromkeys(pid for pid in para_ids if pid))
        if not ids:
            return {}
        rows = pg.execute(
            "SELECT s.sentence_id, s.para_id, s.paper_id, s.section_id, s.text, "
            "s.sequence, p.section_level1 AS section_l1, p.section_level2 AS section_l2 "
            "FROM sentences s JOIN paragraphs p ON p.para_id=s.para_id "
            "WHERE s.para_id = ANY(%s) ORDER BY s.para_id, s.sequence",
            (ids,),
        ).fetchall()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["para_id"], []).append(dict(row))
        return grouped

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        _trace_started = time.perf_counter()
        variants = self._query_variants(query)
        embeddings = self.model.encode(variants, normalize_embeddings=True)
        paragraph_hits = []
        paragraph_rank: Dict[str, int] = {}
        section_hits = []
        paper_hits = []
        lexical = []
        lexical_seen = set()
        lexical_rank: Dict[str, int] = {}
        route_terms = self._route_terms(query) if self.section_routing else []

        pg = self._pg()
        try:
            for variant_index, variant in enumerate(variants):
                hits = self.vector.search(embeddings[variant_index], top_k=self.paragraph_top_k)
                for hit in hits:
                    if hit.para_id not in paragraph_rank:
                        paragraph_rank[hit.para_id] = len(paragraph_rank)
                        paragraph_hits.append(hit)
                for rank, row in enumerate(
                    self._lexical_rows(pg, variant, self.sentence_top_k), start=1
                ):
                    if row["sentence_id"] not in lexical_seen:
                        lexical_seen.add(row["sentence_id"])
                        lexical.append(row)
                    lexical_rank[row["sentence_id"]] = min(
                        lexical_rank.get(row["sentence_id"], rank), rank
                    )
            if route_terms:
                for hit in self.vector.search(
                    embeddings[0], top_k=self.paragraph_top_k, section_terms=route_terms
                ):
                    if hit.para_id not in paragraph_rank:
                        paragraph_rank[hit.para_id] = len(paragraph_rank)
                        paragraph_hits.append(hit)
                        section_hits.append(hit)
                for rank, row in enumerate(
                    self._lexical_rows(
                        pg, query, self.sentence_top_k, section_terms=route_terms
                    ),
                    start=1,
                ):
                    if row["sentence_id"] not in lexical_seen:
                        lexical_seen.add(row["sentence_id"])
                        lexical.append(row)
                    lexical_rank[row["sentence_id"]] = min(
                        lexical_rank.get(row["sentence_id"], rank), rank
                    )
            if self.paper_vector and self.paper_vector_search is not None:
                paper_rows = self.paper_vector_search.search(
                    embeddings[0], top_k=self.paper_vector_top_k
                )
                for paper_row in paper_rows:
                    paper_id = paper_row["paper_id"]
                    for hit in self.vector.search(
                        embeddings[0],
                        top_k=self.paper_paragraphs_per_paper,
                        paper_id=paper_id,
                    ):
                        if hit.para_id in paragraph_rank:
                            continue
                        paragraph_rank[hit.para_id] = len(paragraph_rank)
                        paper_hits.append(hit)
            elif self.paper_candidates:
                paper_ids = self._paper_candidates(
                    pg, query, self.paper_candidates_top_k
                )
                for paper_id in paper_ids:
                    para_ids = self._paragraphs_for_paper(
                        pg, paper_id, query, self.paper_paragraphs_per_paper
                    )
                    for para_id in para_ids:
                        if para_id in paragraph_rank:
                            continue
                        paragraph_rank[para_id] = len(paragraph_rank)
                        paper_hits.append(SimpleNamespace(para_id=para_id))
            by_paragraph = self._sentences_for_paragraphs(
                pg, [hit.para_id for hit in paragraph_hits]
                + [hit.para_id for hit in paper_hits]
            )
        finally:
            pg.close()

        candidates: Dict[str, Dict[str, Any]] = {}
        for row in lexical:
            candidates[row["sentence_id"]] = dict(row)
        for rows in by_paragraph.values():
            for row in rows:
                candidates.setdefault(row["sentence_id"], dict(row))

        scored = []
        for sentence_id, row in candidates.items():
            lex = self.lexical_weight / (60 + lexical_rank[sentence_id]) if sentence_id in lexical_rank else 0.0
            prior_rank = paragraph_rank.get(row["para_id"])
            prior = self.paragraph_weight / (60 + prior_rank) if prior_rank is not None else 0.0
            section_bonus = 0.0
            if route_terms:
                section_text = (
                    f"{row.get('section_l1') or ''} {row.get('section_l2') or ''}"
                ).lower()
                if any(term in section_text for term in route_terms):
                    section_bonus = self.section_boost
            scored.append((lex + prior + section_bonus, row, lex, prior, prior_rank))
        scored.sort(key=lambda item: (-item[0], item[1]["sentence_id"]))

        # Keep a few sentences from each top paragraph in the rerank pool.
        # Without this, a paragraph whose sentences do not match lexically is
        # represented only by its prior and is cut before the cross-encoder.
        meta_by_id = {row["sentence_id"]: (score, row, lex, prior, prior_rank) for score, row, lex, prior, prior_rank in scored}
        pool = []
        chosen = set()
        pool_hits = (section_hits + paragraph_hits)[:15]
        if paper_hits:
            pool_hits = pool_hits + paper_hits[:5]
        for hit in pool_hits:
            rows = sorted(by_paragraph.get(hit.para_id, []), key=lambda row: row.get("sequence") or 0)
            if not rows:
                continue
            picks = rows[:3]
            lexical_rows = [row for row in rows if row["sentence_id"] in lexical_rank]
            if lexical_rows:
                best = min(lexical_rows, key=lambda row: lexical_rank[row["sentence_id"]])
                if best not in picks:
                    picks[-1] = best
            for row in picks:
                if row["sentence_id"] not in chosen:
                    pool.append(meta_by_id[row["sentence_id"]])
                    chosen.add(row["sentence_id"])
        pool_limit = max(self.rerank_pool, 65) if paper_hits else self.rerank_pool
        for item in scored:
            if len(pool) >= pool_limit:
                break
            row = item[1]
            if row["sentence_id"] not in chosen:
                pool.append(item)
                chosen.add(row["sentence_id"])
        pool.sort(key=lambda item: -item[0])
        pool = pool[:pool_limit]
        reranked_all = self.reranker.rerank(
            query,
            [
                {
                    "sentence_id": row["sentence_id"],
                    "text": (row.get("text") or "")[:800],
                }
                for _, row, _, _, _ in pool
            ],
            top_k=len(pool),
            batch_size=16,
        )
        rerank_scores = {
            hit["sentence_id"]: hit.get("rerank_score") for hit in reranked_all
        }
        reranked = reranked_all[:top_k]
        by_id = {row["sentence_id"]: (score, row, lex, prior, prior_rank) for score, row, lex, prior, prior_rank in pool}

        anchors = []
        for hit in reranked:
            score, row, lex, prior, prior_rank = by_id[hit["sentence_id"]]
            anchors.append(
                {
                    "sentence_id": row["sentence_id"],
                    "para_id": row["para_id"],
                    "paper_id": row["paper_id"],
                    "text": row.get("text") or "",
                    "score": hit.get("rerank_score"),
                    "lexical_rank": lexical_rank.get(row["sentence_id"]),
                    "paragraph_rank": prior_rank,
                    "lexical_score": lex,
                    "paragraph_prior": prior,
                }
            )

        from services.search import retrieval_trace

        if retrieval_trace.enabled():
            try:
                retrieval_trace.record(
                    query=query,
                    config={
                        "backend": "sentence_hybrid",
                        "lexical_weight": self.lexical_weight,
                        "paragraph_weight": self.paragraph_weight,
                        "section_boost": self.section_boost,
                        "top_k": top_k,
                        "paragraph_top_k": self.paragraph_top_k,
                        "sentence_top_k": self.sentence_top_k,
                        "rerank_pool": self.rerank_pool,
                    },
                    pool=[
                        {
                            "sentence_id": row["sentence_id"],
                            "para_id": row["para_id"],
                            "paper_id": row["paper_id"],
                            "lexical_score": lex,
                            "paragraph_prior": prior,
                            "lexical_rank": lexical_rank.get(row["sentence_id"]),
                            "paragraph_rank": prior_rank,
                            "rerank_score": rerank_scores.get(row["sentence_id"]),
                        }
                        for _, row, lex, prior, prior_rank in pool
                    ],
                    final=anchors,
                    latency_ms=(time.perf_counter() - _trace_started) * 1000,
                )
            except Exception:
                pass

        pg = self._pg()
        try:
            context_rows = self._sentences_for_paragraphs(
                pg, [anchor["para_id"] for anchor in anchors]
            )
        finally:
            pg.close()

        units = []
        for anchor in anchors:
            unit = build_context(
                anchor,
                context_rows.get(anchor["para_id"], []),
                query=query,
                policy=self.context_policy,
            )
            units.append(unit.as_dict())
        return units


    def search_hits(self, query: str, top_k: int = 10) -> "RetrievalResult":
        """Return the stable experiment contract for sentence retrieval."""
        from services.search.result import result_from_sentence_units

        return result_from_sentence_units(
            query, self.search(query, top_k=top_k), source="sentence_backend"
        )

    def to_evidence_json(self, query: str, paper_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        top_k = int(kwargs.get("top_paragraphs") or kwargs.get("top_k") or 10)
        units = self.search(query, top_k=top_k)
        if paper_id:
            units = [unit for unit in units if unit.get("paper_id") == paper_id]
        return units_to_evidence_json(query, units)
