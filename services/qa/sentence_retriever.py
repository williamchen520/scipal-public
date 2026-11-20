"""QA adapter over the accepted sentence evidence retriever."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class SentenceQARetriever:
    """Expose the sentence retriever through QAService's retrieval contract."""

    def __init__(self, base=None) -> None:
        if base is None:
            from services.search.sentence_hybrid import SentenceHybridRetriever

            base = SentenceHybridRetriever()
        self.base = base

    def retrieve(
        self,
        question: str,
        paper_id: Optional[str] = None,
        top_paragraphs: int = 10,
        top_figures: int = 3,
        allowed_paper_ids: Optional[set[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        units = self.base.search(question, top_k=top_paragraphs)
        if paper_id:
            units = [unit for unit in units if unit.get("paper_id") == paper_id]
        if allowed_paper_ids is not None:
            units = [
                unit for unit in units if unit.get("paper_id") in allowed_paper_ids
            ]
        paragraphs = []
        for index, unit in enumerate(units, 1):
            paragraphs.append(
                {
                    "para_id": unit.get("para_id"),
                    "paper_id": unit.get("paper_id"),
                    "sentence_id": unit.get("sentence_id") or unit.get("anchor_sentence_id") or "",
                    "text": unit.get("text") or unit.get("anchor_text") or "",
                    "section_l1": (unit.get("section_path") or [""])[0]
                    if unit.get("section_path")
                    else "",
                    "section_path": unit.get("section_path") or [],
                    "page": unit.get("page"),
                    "score": unit.get("anchor_score"),
                    "retrieval_score": unit.get("anchor_score"),
                    "rerank_score": unit.get("rerank_score"),
                    "rank": index,
                }
            )
        return {
            "question": question,
            "paragraphs": paragraphs,
            "parent_contexts": paragraphs,
            "figures": [],
            "tables": [],
            "papers": [],
            "chunks": [],
            "summaries": [],
            "evidence": paragraphs,
            "route": {"channels": ["qa"], "primary": "sentence"},
        }

    @staticmethod
    def envelope_from_result(question: str, env: Dict[str, Any]) -> str:
        lines = [f"QUERY: {question}", "=" * 50, "EVIDENCE:"]
        for index, item in enumerate(env.get("parent_contexts") or [], 1):
            section = item.get("section_l1") or ""
            tag = f" ({section})" if section else ""
            lines.append(f"[P{index}]{tag}\n{item.get('text', '')}")
        lines.append("=" * 50)
        lines.append("Cite evidence using the IDs above (e.g. [P1]).")
        return "\n".join(lines)

    def to_envelope(self, question: str, **kwargs) -> str:
        return self.envelope_from_result(question, self.retrieve(question, **kwargs))
