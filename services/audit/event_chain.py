"""Per-answer append-only event hash chain."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64
_LOCK = threading.Lock()


def _pg_enabled() -> bool:
    return os.environ.get("SCIPAL_AUDIT_PG", "").strip().lower() in {"1", "true", "yes", "on"}


def chain_path() -> Path:
    return Path(os.environ.get("SCIPAL_EVENT_CHAIN_PATH", "logs/ledger-event-chain.jsonl"))


def _canonical(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _rows() -> list[dict[str, Any]]:
    path = chain_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(chain_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if _pg_enabled():
        from services.audit.pg_store import append_chain
        return append_chain(chain_id, event_type, payload)
    events = [row for row in _rows() if row.get("chain_id") == chain_id]
    prev = events[-1]["event_hash"] if events else GENESIS
    event = {
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "chain_id": chain_id,
        "event_type": event_type,
        "payload": payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prev_event_hash": prev,
    }
    event["event_hash"] = hashlib.sha256((prev + _canonical(event)).encode("utf-8")).hexdigest()
    path = chain_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def verify(chain_id: str) -> dict[str, Any]:
    if _pg_enabled():
        from services.audit.pg_store import verify_chain
        return verify_chain(chain_id)
    events = [row for row in _rows() if row.get("chain_id") == chain_id]
    expected_prev = GENESIS
    for index, event in enumerate(events):
        body = {key: value for key, value in event.items() if key != "event_hash"}
        actual = hashlib.sha256((expected_prev + _canonical(body)).encode("utf-8")).hexdigest()
        if event.get("prev_event_hash") != expected_prev or event.get("event_hash") != actual:
            return {"ok": False, "events": len(events), "broken_at": index, "event_id": event.get("event_id")}
        expected_prev = event["event_hash"]
    return {"ok": True, "events": len(events), "head": expected_prev}
