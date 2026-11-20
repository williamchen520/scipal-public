"""Audit Record v1: evidence provenance, not ranking.

This module is deliberately read-only and framework-free. It can be attached to
any retrieval bundle without changing retrieval behavior.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1"
REQUIRED = ("schema_version", "audit_id", "created_at", "query", "retrieval", "evidence", "coverage")
STOPWORDS = {
    "the", "and", "for", "with", "what", "which", "how", "does", "did", "was",
    "were", "are", "is", "of", "in", "to", "on", "by", "a", "an", "that", "this",
    "from", "as", "at", "or", "be", "been", "between", "into", "about", "when",
}


def extract_facets(query: str, limit: int = 12) -> list[str]:
    terms = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query or "")
    facets = []
    seen = set()
    for term in terms:
        key = term.lower()
        if key in STOPWORDS or key in seen:
            continue
        seen.add(key)
        facets.append(key)
        if len(facets) >= limit:
            break
    return facets


def _refs(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    refs = []
    for item in bundle.get("evidence") or []:
        paper_id = item.get("paper_id") or ""
        para_id = item.get("para_id") or ""
        for highlight in item.get("highlight") or []:
            refs.append({
                "paper_id": paper_id,
                "para_id": para_id,
                "sentence_id": highlight.get("sentence_id") or "",
                "page": highlight.get("page"),
                "bbox": highlight.get("bbox"),
                "text": (highlight.get("text") or "")[:500],
            })
    return refs


def build_audit_record(
    *,
    query: str,
    bundle: dict[str, Any],
    config_id: str = "",
    trace_id: str = "",
    snapshot_id: str = "",
    facets: list[str] | None = None,
) -> dict[str, Any]:
    refs = _refs(bundle)
    missing = [
        ref for ref in refs
        if not ref["paper_id"] or not ref["para_id"] or not ref["sentence_id"]
    ]
    provenance_complete = bool(refs) and not missing and all(
        ref["paper_id"] and ref["para_id"] and ref["sentence_id"] for ref in refs
    )
    facet_terms = [facet for facet in (facets if facets is not None else extract_facets(query)) if facet]
    evidence_text = " ".join(ref.get("text") or "" for ref in refs).casefold()
    facet_details = [
        {"facet": facet, "covered": facet.casefold() in evidence_text}
        for facet in facet_terms
    ]
    covered_facets = [row["facet"] for row in facet_details if row["covered"]]
    missing_facets = [row["facet"] for row in facet_details if not row["covered"]]
    if not refs:
        status = "empty"
        facet_status = "uncovered" if facet_terms else "not_computed"
    elif not provenance_complete:
        status = "partial"
        facet_status = "partial" if covered_facets else "uncovered"
    else:
        status = "covered"
        facet_status = "covered" if not missing_facets else ("partial" if covered_facets else "uncovered")
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_id": f"aud_{uuid.uuid4().hex[:16]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "retrieval": {
            "config_id": config_id,
            "trace_id": trace_id,
            "snapshot_id": snapshot_id,
            "backend": (bundle.get("sufficiency") or {}).get("reason", ""),
            "evidence_count": len(refs),
            "unique_papers": len({ref["paper_id"] for ref in refs if ref["paper_id"]}),
        },
        "evidence": refs,
        "coverage": {
            "status": status,
            "facets": covered_facets,
            "facet_details": facet_details,
            "facet_status": facet_status,
            "missing_facet_count": len(missing_facets),
            "provenance_complete": provenance_complete,
            "claim_coverage": "not_computed",
            "missing_provenance": [
                {"paper_id": ref["paper_id"], "sentence_id": ref["sentence_id"]}
                for ref in missing
            ],
        },
    }


def validate_audit_record(record: dict[str, Any]) -> list[str]:
    errors = []
    for key in REQUIRED:
        if key not in record:
            errors.append(f"missing field: {key}")
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if not isinstance(record.get("evidence"), list):
        errors.append("evidence must be a list")
    if not isinstance(record.get("coverage"), dict):
        errors.append("coverage must be an object")
    if not record.get("query"):
        errors.append("query is required")
    for index, ref in enumerate(record.get("evidence") or []):
        if not ref.get("paper_id") or not ref.get("para_id") or not ref.get("sentence_id"):
            errors.append(f"evidence[{index}] missing paper_id/para_id/sentence_id")
    return errors
