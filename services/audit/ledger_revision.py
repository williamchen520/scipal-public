"""Create a new ledger version from a review action. Never mutates the old one."""

from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from services.audit.evidence_ledger import refresh
from services.audit.ledger_contract import text_hash

REVISION_ACTIONS = {"remove_claim", "add_evidence", "flag_missing", "rewrite_claim"}
CITE_RE = re.compile(r"\[P(\d+)\]")


def revise(
    ledger: dict[str, Any],
    *,
    action: str,
    target_id: str,
    note: str = "",
    evidence: dict[str, Any] | None = None,
    new_text: str = "",
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    if action not in REVISION_ACTIONS:
        raise ValueError(f"action must be one of {sorted(REVISION_ACTIONS)}")
    new = copy.deepcopy(ledger)
    new["answer_id"] = f"ans_{uuid.uuid4().hex[:12]}"
    new["parent_answer_id"] = ledger.get("answer_id", "")
    new["chain_id"] = ledger.get("chain_id") or ledger.get("answer_id", "")
    new["revision"] = int(ledger.get("revision") or 1) + 1
    new["answer_text_hash"] = text_hash(new.get("answer") or "")
    new["created_at"] = datetime.now(timezone.utc).isoformat()
    new["source_action"] = {"action": action, "target_id": target_id, "note": note}

    if action == "remove_claim":
        before = len(new.get("claims") or [])
        new["claims"] = [row for row in new.get("claims") or [] if row.get("claim_id") != target_id]
        if len(new["claims"]) == before:
            raise ValueError("claim not found")
    elif action == "add_evidence":
        if not evidence or not evidence.get("sentence_id"):
            raise ValueError("evidence with sentence_id required")
        ref = {
            "sentence_id": evidence.get("sentence_id", ""),
            "paper_id": evidence.get("paper_id", ""),
            "para_id": evidence.get("para_id", ""),
            "title": evidence.get("title", ""),
            "section": evidence.get("section", ""),
            "page": evidence.get("page"),
            "text": evidence.get("text", "")[:800],
            "retrieval_score": evidence.get("retrieval_score"),
            "rerank_score": evidence.get("rerank_score"),
            "rank": evidence.get("rank") or len(new.get("evidence") or []) + 1,
        }
        if not any(row.get("sentence_id") == ref["sentence_id"] for row in new.get("evidence") or []):
            new.setdefault("evidence", []).append(ref)
        claim = next((row for row in new.get("claims") or [] if row.get("claim_id") == target_id), None)
        if claim is None:
            raise ValueError("claim not found")
        if ref["sentence_id"] not in (claim.get("cited_sentence_ids") or []):
            claim.setdefault("cited_sentence_ids", []).append(ref["sentence_id"])
    elif action == "rewrite_claim":
        if not new_text.strip():
            raise ValueError("new_text required")
        claim = next((row for row in new.get("claims") or [] if row.get("claim_id") == target_id), None)
        if claim is None:
            raise ValueError("claim not found")
        labels = [int(match.group(1)) for match in CITE_RE.finditer(new_text)]
        if not evidence_ids:
            raise ValueError("evidence_ids required for rewrite_claim")
        if any(label < 1 or label > len(evidence_ids) for label in labels):
            raise ValueError("rewrite cites out-of-scope evidence")
        claim["text"] = new_text[:2000]
        claim["cited_sentence_ids"] = list(evidence_ids)
    elif action == "flag_missing":
        new.setdefault("unresolved", []).append({"target_id": target_id, "note": note[:500]})

    refresh(new)
    return new
