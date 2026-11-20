"""Outbox regeneration handler: evidence-constrained rewrite -> repaired ledger."""

from __future__ import annotations

from typing import Any

from services.audit.error_lifecycle import get as get_error, transition as transition_error
from services.audit.ledger_revision import revise
from services.audit.ledger_store import get_ledger, save
from services.audit.ledger_verification import verify_ledger
from services.qa.evidence_rewrite import rewrite


def handle(job: dict[str, Any]) -> dict[str, Any]:
    ledger = get_ledger(job["answer_id"])
    error = get_error(job["error_id"])
    if ledger is None or error is None:
        raise ValueError("ledger or error not found")
    if error.get("status") in {"repaired", "verified", "closed"} and error.get("revision_answer_id"):
        return {
            "ledger": get_ledger(error["revision_answer_id"]),
            "error_id": error["error_id"],
            "rewrite": {"status": "already_repaired"},
        }
    claim_id = error.get("target_id") or ""
    claim = next((row for row in ledger.get("claims") or [] if row.get("claim_id") == claim_id), None)
    if claim is None:
        raise ValueError("claim not found")
    if error.get("error_type") == "remove_claim":
        new_ledger = revise(ledger, action="remove_claim", target_id=claim_id)
        verification = verify_ledger(new_ledger)
        if not verification["ok"]:
            raise ValueError(f"verification failed: {verification['errors']}")
        save(new_ledger)
        transition_error(error["error_id"], "triaged", actor="outbox")
        transition_error(error["error_id"], "repair_proposed", actor="outbox")
        transition_error(
            error["error_id"], "repaired", actor="outbox",
            revision_answer_id=new_ledger["answer_id"], diff="outbox claim removal",
        )
        return {"ledger": new_ledger, "error_id": error["error_id"], "rewrite": {"status": "removed"}}

    ids = claim.get("cited_sentence_ids") or [
        ref.get("sentence_id") for ref in (ledger.get("evidence") or [])[:6]
    ]
    evidence = [ref for ref in ledger.get("evidence") or [] if ref.get("sentence_id") in ids]
    if not evidence:
        raise ValueError("no evidence for claim")

    from services.qa.qa_service import QAService

    llm = QAService._create_llm_from_env()
    result = rewrite(
        question=str(ledger.get("query") or ""),
        paragraph=str(claim.get("text") or ""),
        evidence=evidence,
        llm=llm,
        instruction=str((job.get("payload") or {}).get("note") or ""),
    )
    if result["status"] != "draft":
        raise ValueError(f"rewrite rejected: {result.get('reason') or result['status']}")

    new_ledger = revise(
        ledger,
        action="rewrite_claim",
        target_id=claim_id,
        new_text=result["draft"],
        evidence_ids=result.get("used_sentence_ids") or ids,
        note="outbox regeneration",
    )
    verification = verify_ledger(new_ledger)
    if not verification["ok"]:
        raise ValueError(f"verification failed: {verification['errors']}")
    save(new_ledger)
    transition_error(error["error_id"], "triaged", actor="outbox")
    transition_error(error["error_id"], "repair_proposed", actor="outbox")
    transition_error(
        error["error_id"],
        "repaired",
        actor="outbox",
        revision_answer_id=new_ledger["answer_id"],
        diff="outbox evidence-constrained rewrite",
    )
    return {"ledger": new_ledger, "error_id": error["error_id"], "rewrite": result}
