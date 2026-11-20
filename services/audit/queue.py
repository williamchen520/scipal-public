"""Append-only audit exception queue (local JSONL, no answer text)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def queue_path() -> Path:
    return Path(os.environ.get("SCIPAL_AUDIT_QUEUE_PATH", "logs/audit-queue.jsonl"))


def state_path() -> Path:
    return Path(os.environ.get("SCIPAL_AUDIT_QUEUE_STATE_PATH", "logs/audit-queue-state.jsonl"))


def _reasons(audit: dict[str, Any] | None, claim_audit: dict[str, Any] | None) -> list[str]:
    reasons = []
    coverage = (audit or {}).get("coverage") or {}
    if coverage.get("facet_status") in {"partial", "uncovered"}:
        reasons.append(f"facet_{coverage['facet_status']}")
    if coverage.get("status") == "empty":
        reasons.append("no_evidence")
    elif coverage and not coverage.get("provenance_complete", True):
        reasons.append("provenance_incomplete")
    if claim_audit:
        if claim_audit.get("status") in {"partial", "uncovered"}:
            reasons.append(f"claim_{claim_audit['status']}")
        if claim_audit.get("unknown_citations"):
            reasons.append("unknown_citations")
        if claim_audit.get("claims_total") and not claim_audit.get("verification_ok", True):
            reasons.append("verification_failed")
    return sorted(set(reasons))


def enqueue(
    *,
    audit: dict[str, Any] | None = None,
    claim_audit: dict[str, Any] | None = None,
    source: str = "evidence",
) -> dict[str, Any] | None:
    reasons = _reasons(audit, claim_audit)
    if not reasons:
        return None
    coverage = (audit or {}).get("coverage") or {}
    event = {
        "queue_id": f"aq_{uuid.uuid4().hex[:12]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "audit_id": (audit or {}).get("audit_id", ""),
        "query": (audit or {}).get("query", ""),
        "config_id": ((audit or {}).get("retrieval") or {}).get("config_id", ""),
        "reasons": reasons,
        "facet_status": coverage.get("facet_status", ""),
        "provenance_complete": coverage.get("provenance_complete"),
        "claim_status": (claim_audit or {}).get("status", ""),
        "verification_ok": (claim_audit or {}).get("verification_ok"),
    }
    path = queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def mark(queue_id: str, status: str, note: str = "") -> dict[str, Any] | None:
    if status not in {"reviewed", "dismissed"}:
        raise ValueError("status must be reviewed or dismissed")
    if not any(row.get("queue_id") == queue_id for row in list_events(100000)):
        return None
    event = {
        "queue_id": queue_id,
        "status": status,
        "note": note[:500],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    path = queue_path()
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    states: dict[str, dict[str, Any]] = {}
    state = state_path()
    if state.exists():
        for line in state.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                states[item["queue_id"]] = item
    for row in rows:
        state_row = states.get(row["queue_id"]) or {}
        row["status"] = state_row.get("status", "open")
        row["review_note"] = state_row.get("note", "")
    return rows[-max(1, min(limit, 1000)):]
