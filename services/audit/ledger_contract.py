"""Contract checks for the evidence ledger (D1/D2)."""

from __future__ import annotations

import hashlib
from typing import Any

UNIT_ROLES = {"evidence", "answer_claim", "manuscript_claim"}


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def validate_contract(ledger: dict[str, Any]) -> list[str]:
    errors = []
    for claim in ledger.get("claims") or []:
        if claim.get("unit_role") not in {"answer_claim", "manuscript_claim"}:
            errors.append(f"{claim.get('claim_id')}: invalid claim unit_role")
        if not claim.get("answer_version_id"):
            errors.append(f"{claim.get('claim_id')}: missing answer_version_id")
    for ref in ledger.get("evidence") or []:
        if ref.get("unit_role") != "evidence":
            errors.append(f"{ref.get('sentence_id')}: invalid evidence unit_role")
        source = ref.get("source_ref") or {}
        if source:
            if not source.get("version"):
                errors.append(f"{ref.get('sentence_id')}: source_ref.version required")
            if not source.get("content_hash"):
                errors.append(f"{ref.get('sentence_id')}: source_ref.content_hash required")
    if ledger.get("answer_text_hash") and ledger["answer_text_hash"] != text_hash(ledger.get("answer") or ""):
        errors.append("answer_text_hash mismatch")
    return errors
