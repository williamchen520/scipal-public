"""Structural claim audit: claims -> citation markers -> verification status."""

from __future__ import annotations

import re
from typing import Any

from services.qa.semantic_grounding import split_claims
from services.qa.verify import CITE_RE

SCHEMA_VERSION = "1"


def build_claim_audit(
    *,
    answer: str,
    citations: list[dict[str, Any]] | None = None,
    verification: dict[str, Any] | None = None,
    grounding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    claims = split_claims(answer or "")
    rows = []
    cited_count = 0
    for claim in claims:
        markers = sorted({match.group(0) for match in CITE_RE.finditer(claim)})
        cited = bool(markers)
        if cited:
            cited_count += 1
        rows.append({"claim": claim[:500], "cited": cited, "citations": markers})
    if not claims:
        status = "not_computed"
    elif cited_count == len(claims):
        status = "covered"
    elif cited_count:
        status = "partial"
    else:
        status = "uncovered"
    verification = verification or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "claims_total": len(claims),
        "claims_cited": cited_count,
        "citation_coverage": round(cited_count / len(claims), 4) if claims else None,
        "status": status,
        "claims": rows,
        "unknown_citations": list(verification.get("missing_ids") or []),
        "verification_ok": bool(verification.get("ok")),
        "grounding": grounding,
        "citations": list(citations or []),
    }
