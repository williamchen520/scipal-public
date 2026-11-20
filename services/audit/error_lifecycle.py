"""Append-only error lifecycle for ledger review findings."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = {"detected", "triaged", "repair_proposed", "repaired", "verified", "closed", "unresolved"}
TRANSITIONS = {
    "detected": {"triaged", "unresolved"},
    "triaged": {"repair_proposed", "unresolved"},
    "repair_proposed": {"repaired", "unresolved"},
    "repaired": {"verified", "unresolved"},
    "verified": {"closed", "unresolved"},
    "closed": set(),
    "unresolved": {"triaged"},
}
_LOCK = threading.Lock()


def _pg_enabled() -> bool:
    return os.environ.get("SCIPAL_AUDIT_PG", "").strip().lower() in {"1", "true", "yes", "on"}


def path() -> Path:
    return Path(os.environ.get("SCIPAL_ERRORS_PATH", "logs/audit-errors.jsonl"))


def _append(event: dict[str, Any]) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _events() -> list[dict[str, Any]]:
    target = path()
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def create(
    *,
    answer_id: str,
    error_type: str,
    target_id: str,
    note: str = "",
    actor: str = "",
    severity: str = "medium",
    status: str = "detected",
    revision_answer_id: str = "",
    diff: str = "",
) -> dict[str, Any]:
    if status not in {"detected", "repaired"}:
        raise ValueError("initial status must be detected or repaired")
    error_id = f"err_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "event": "created",
        "error_id": error_id,
        "answer_id": answer_id,
        "error_type": error_type,
        "target_id": target_id,
        "severity": severity,
        "status": status,
        "note": note[:500],
        "actor": actor,
        "revision_answer_id": revision_answer_id,
        "diff": diff[:2000],
        "created_at": now,
        "updated_at": now,
    }
    if _pg_enabled():
        from services.audit.pg_store import create_error
        return create_error(event)
    _append(event)
    return event


def get(error_id: str) -> dict[str, Any] | None:
    if _pg_enabled():
        from services.audit.pg_store import get_error
        return get_error(error_id)
    rows = [row for row in _events() if row.get("error_id") == error_id]
    return rows[-1] if rows else None


def transition(
    error_id: str,
    status: str,
    *,
    note: str = "",
    actor: str = "",
    revision_answer_id: str = "",
    verification_ok: bool = False,
    diff: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    current = get(error_id)
    if current is None:
        raise KeyError(error_id)
    if status not in TRANSITIONS[current["status"]]:
        raise ValueError(f"invalid transition {current['status']} -> {status}")
    if status == "closed":
        missing = []
        if not revision_answer_id:
            missing.append("revision_answer_id")
        if not verification_ok:
            missing.append("verification_ok=true")
        if not diff.strip():
            missing.append("diff")
        if missing:
            raise ValueError("closed requires " + ", ".join(missing))
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "event": "transition",
        "error_id": error_id,
        "answer_id": current.get("answer_id", ""),
        "error_type": current.get("error_type", ""),
        "target_id": current.get("target_id", ""),
        "severity": current.get("severity", "medium"),
        "status": status,
        "note": note[:500],
        "actor": actor,
        "revision_answer_id": revision_answer_id,
        "verification_ok": bool(verification_ok),
        "diff": diff[:2000],
        "created_at": current.get("created_at", now),
        "updated_at": now,
    }
    if _pg_enabled():
        from services.audit.pg_store import transition_error
        return transition_error(error_id, event)
    _append(event)
    return event


def list_errors(limit: int = 100) -> list[dict[str, Any]]:
    if _pg_enabled():
        from services.audit.pg_store import list_errors as pg_list
        return pg_list(limit)
    latest: dict[str, dict[str, Any]] = {}
    for event in _events():
        latest[event["error_id"]] = event
    items = sorted(latest.values(), key=lambda row: row.get("updated_at", ""), reverse=True)
    return items[:max(1, min(limit, 1000))]
