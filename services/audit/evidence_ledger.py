"""Evidence ledger: answer-level claim/evidence accounting for human review."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from services.audit.ledger_contract import text_hash

SCHEMA_VERSION = "1"
PRIORITY_RULES = {
    "cited_low_score": 0.3,
    "uncited_high_score": 0.8,
    "uncited_medium_score": 0.5,
}


def _score(item: dict[str, Any]) -> float:
    value = item.get("rerank_score")
    if value is None:
        value = item.get("retrieval_score")
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _provenance_ok(item: dict[str, Any]) -> bool:
    return bool(item.get("paper_id") and item.get("sentence_id"))


def _priority(item: dict[str, Any], cited: bool) -> str:
    score = _score(item)
    if cited:
        if not _provenance_ok(item) or score < PRIORITY_RULES["cited_low_score"]:
            return "high"
        return "low"
    if not _provenance_ok(item):
        return "high"
    if score >= PRIORITY_RULES["uncited_high_score"]:
        return "high"
    if score >= PRIORITY_RULES["uncited_medium_score"]:
        return "medium"
    return "low"


def build_ledger(
    *,
    query: str,
    answer: str,
    evidence: list[dict[str, Any]],
    claims: list[dict[str, Any]] | None = None,
    corpus_snapshot_id: str = "",
    scope: dict[str, Any] | None = None,
    config_id: str = "",
) -> dict[str, Any]:
    answer_id = f"ans_{uuid.uuid4().hex[:12]}"
    refs = []
    for rank, item in enumerate(evidence, 1):
        ref = {
            "sentence_id": item.get("sentence_id") or "",
            "paper_id": item.get("paper_id") or "",
            "para_id": item.get("para_id") or "",
            "title": item.get("title") or "",
            "section": item.get("section") or "",
            "page": item.get("page"),
            "text": (item.get("text") or "")[:800],
            "retrieval_score": item.get("retrieval_score"),
            "rerank_score": item.get("rerank_score"),
            "rank": item.get("rank") or rank,
            "unit_role": "evidence",
            "source_ref": {
                "kind": "literature",
                "doc_id": item.get("paper_id") or "",
                "version": corpus_snapshot_id,
                "content_hash": text_hash(item.get("text") or ""),
                "locator": {
                    "paragraph": item.get("para_id") or "",
                    "sentence": item.get("sentence_id") or "",
                    "page": item.get("page"),
                },
            },
        }
        refs.append(ref)
    by_sentence = {ref["sentence_id"]: ref for ref in refs if ref["sentence_id"]}
    claim_rows = []
    for index, claim in enumerate(claims or [], 1):
        cited_ids = [str(sid) for sid in (claim.get("cited_sentence_ids") or [])]
        known = [sid for sid in cited_ids if sid in by_sentence]
        unknown = [sid for sid in cited_ids if sid not in by_sentence]
        if not cited_ids:
            status = "uncited"
        elif unknown:
            status = "unknown_evidence"
        else:
            status = "cited"
        claim_rows.append({
            "claim_id": claim.get("claim_id") or f"cl_{index}",
            "text": (claim.get("text") or "")[:800],
            "cited_sentence_ids": cited_ids,
            "known_sentence_ids": known,
            "unknown_sentence_ids": unknown,
            "support_status": status,
            "unit_role": "answer_claim",
            "answer_version_id": answer_id,
        })
    for claim in claim_rows:
        for sid in claim["known_sentence_ids"]:
            by_sentence[sid]["cited"] = True
    for ref in refs:
        ref["cited"] = bool(ref.get("cited"))
        ref["review_priority"] = _priority(ref, ref["cited"])
    return {
        "schema_version": SCHEMA_VERSION,
        "answer_id": answer_id,
        "chain_id": answer_id,
        "parent_answer_id": "",
        "revision": 1,
        "answer_text_hash": text_hash(answer),
        "renderer_version": "ledger_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "answer": answer,
        "config_id": config_id,
        "corpus_snapshot_id": corpus_snapshot_id,
        "scope": scope or {},
        "claims": claim_rows,
        "evidence": refs,
        "summary": {
            "claims": len(claim_rows),
            "uncited_claims": sum(1 for row in claim_rows if row["support_status"] == "uncited"),
            "unknown_evidence_claims": sum(1 for row in claim_rows if row["support_status"] == "unknown_evidence"),
            "evidence": len(refs),
            "cited_evidence": sum(1 for ref in refs if ref["cited"]),
            "high_priority": sum(1 for ref in refs if ref["review_priority"] == "high"),
        },
    }


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    errors = []
    for key in ("schema_version", "answer_id", "query", "claims", "evidence", "summary"):
        if key not in ledger:
            errors.append(f"missing field: {key}")
    if ledger.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    for index, ref in enumerate(ledger.get("evidence") or []):
        if not ref.get("paper_id") or not ref.get("sentence_id"):
            errors.append(f"evidence[{index}] missing paper_id/sentence_id")
    return errors


_MARKER = re.compile(r"\[P(\d+)\]")


def claims_from_claim_audit(claim_audit: dict[str, Any] | None, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [ref.get("sentence_id") or ref.get("para_id") or "" for ref in evidence]
    claims = []
    for index, row in enumerate((claim_audit or {}).get("claims") or [], 1):
        cited = []
        for marker in row.get("citations") or []:
            match = _MARKER.fullmatch(str(marker))
            if not match:
                continue
            position = int(match.group(1)) - 1
            if 0 <= position < len(ids) and ids[position]:
                cited.append(ids[position])
        claims.append({
            "claim_id": row.get("claim_id") or f"cl_{index}",
            "text": row.get("claim") or "",
            "cited_sentence_ids": cited,
        })
    return claims


def refresh(ledger: dict[str, Any]) -> dict[str, Any]:
    cited = {
        sid
        for claim in ledger.get("claims") or []
        for sid in (claim.get("known_sentence_ids") or claim.get("cited_sentence_ids") or [])
    }
    by_id = {ref.get("sentence_id"): ref for ref in ledger.get("evidence") or []}
    for ref in ledger.get("evidence") or []:
        ref["cited"] = ref.get("sentence_id") in cited
        ref["review_priority"] = _priority(ref, ref["cited"])
    for claim in ledger.get("claims") or []:
        known = [sid for sid in claim.get("cited_sentence_ids") or [] if sid in by_id]
        unknown = [sid for sid in claim.get("cited_sentence_ids") or [] if sid not in by_id]
        claim["known_sentence_ids"] = known
        claim["unknown_sentence_ids"] = unknown
        if not claim.get("cited_sentence_ids"):
            claim["support_status"] = "uncited"
        elif unknown:
            claim["support_status"] = "unknown_evidence"
        else:
            claim["support_status"] = "cited"
    ledger["summary"] = {
        "claims": len(ledger.get("claims") or []),
        "uncited_claims": sum(1 for row in ledger.get("claims") or [] if row.get("support_status") == "uncited"),
        "unknown_evidence_claims": sum(1 for row in ledger.get("claims") or [] if row.get("support_status") == "unknown_evidence"),
        "evidence": len(ledger.get("evidence") or []),
        "cited_evidence": sum(1 for ref in ledger.get("evidence") or [] if ref.get("cited")),
        "high_priority": sum(1 for ref in ledger.get("evidence") or [] if ref.get("review_priority") == "high"),
    }
    return ledger
