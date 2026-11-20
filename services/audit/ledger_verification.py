"""Server-side verification and diff for ledger revisions."""

from __future__ import annotations

from typing import Any


def verify_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    errors = []
    evidence_ids = {ref.get("sentence_id") for ref in ledger.get("evidence") or []}
    claims = ledger.get("claims") or []
    if not claims:
        errors.append("no_claims")
    for claim in claims:
        cited = claim.get("cited_sentence_ids") or []
        if not cited:
            errors.append(f"{claim.get('claim_id')}: uncited")
        for sid in cited:
            if sid not in evidence_ids:
                errors.append(f"{claim.get('claim_id')}: unknown_evidence:{sid}")
    for ref in ledger.get("evidence") or []:
        if not ref.get("paper_id") or not ref.get("sentence_id"):
            errors.append(f"provenance:{ref.get('sentence_id') or '?'}")
    return {
        "ok": not errors,
        "errors": errors,
        "claims": len(claims),
        "evidence": len(ledger.get("evidence") or []),
    }


def diff_ledgers(parent: dict[str, Any] | None, revision: dict[str, Any]) -> str:
    old_claims = {row.get("claim_id"): row.get("text", "") for row in (parent or {}).get("claims") or []}
    new_claims = {row.get("claim_id"): row.get("text", "") for row in revision.get("claims") or []}
    removed = sorted(set(old_claims) - set(new_claims))
    added = sorted(set(new_claims) - set(old_claims))
    changed = sorted(
        key for key in set(old_claims) & set(new_claims)
        if old_claims[key] != new_claims[key]
    )
    old_evidence = len((parent or {}).get("evidence") or [])
    new_evidence = len(revision.get("evidence") or [])
    return (
        f"claims removed={removed} added={added} changed={changed}; "
        f"evidence {old_evidence}->{new_evidence}"
    )
