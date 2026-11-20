"""PostgreSQL storage for audit ledgers (Q5, phase 1)."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from services.db.pg_pool import core_connection

GENESIS = "0" * 64


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def save_ledger(ledger: dict[str, Any]) -> None:
    with core_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_ledger
              (answer_id, chain_id, parent_answer_id, revision, query, answer_text,
               answer_text_hash, config_id, corpus_snapshot_id, payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (answer_id) DO NOTHING
            """,
            (
                ledger.get("answer_id", ""),
                ledger.get("chain_id") or ledger.get("answer_id", ""),
                ledger.get("parent_answer_id", ""),
                int(ledger.get("revision") or 1),
                ledger.get("query", ""),
                ledger.get("answer", ""),
                ledger.get("answer_text_hash", ""),
                ledger.get("config_id", ""),
                ledger.get("corpus_snapshot_id", ""),
                _json(ledger),
            ),
        )


def list_ledgers(limit: int = 50) -> list[dict[str, Any]]:
    with core_connection() as conn:
        rows = conn.execute(
            """
            SELECT answer_id, created_at, query, config_id, corpus_snapshot_id,
                   payload->'summary' AS summary
            FROM audit_ledger
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (max(1, min(limit, 1000)),),
        ).fetchall()
    return [
        {
            "answer_id": row["answer_id"],
            "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
            "query": row["query"],
            "config_id": row["config_id"],
            "corpus_snapshot_id": row["corpus_snapshot_id"],
            "summary": row.get("summary") or {},
        }
        for row in rows
    ]


def get_ledger(answer_id: str) -> dict[str, Any] | None:
    with core_connection() as conn:
        row = conn.execute(
            "SELECT payload FROM audit_ledger WHERE answer_id = %s",
            (answer_id,),
        ).fetchone()
    if not row:
        return None
    payload = row["payload"]
    return payload if isinstance(payload, dict) else json.loads(payload)


def _canonical(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_action(event: dict[str, Any]) -> dict[str, Any]:
    return append_chain(event.get("answer_id", ""), "action", event)


def list_actions(answer_id: str) -> list[dict[str, Any]]:
    with core_connection() as conn:
        rows = conn.execute(
            "SELECT payload FROM audit_event WHERE answer_id=%s AND event_type='action' ORDER BY created_at, event_id",
            (answer_id,),
        ).fetchall()
    return [row["payload"] for row in rows]


def append_chain(chain_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    with core_connection() as conn:
        last = conn.execute(
            "SELECT event_hash FROM audit_event WHERE chain_id=%s ORDER BY created_at DESC, event_id DESC LIMIT 1",
            (chain_id,),
        ).fetchone()
        prev = last["event_hash"] if last else GENESIS
        event = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "chain_id": chain_id,
            "answer_id": payload.get("answer_id") or payload.get("answer", {}).get("answer_id", ""),
            "event_type": event_type,
            "payload": payload,
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "prev_event_hash": prev,
        }
        event["event_hash"] = hashlib.sha256((prev + _canonical(event)).encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO audit_event(event_id,chain_id,answer_id,event_type,payload,prev_event_hash,event_hash,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (event["event_id"], chain_id, event["answer_id"], event_type, _json(payload), prev, event["event_hash"], event["created_at"]),
        )
    return event


def verify_chain(chain_id: str) -> dict[str, Any]:
    with core_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_event WHERE chain_id=%s ORDER BY created_at, event_id",
            (chain_id,),
        ).fetchall()
    expected = GENESIS
    for index, row in enumerate(rows):
        body = {
            "event_id": row["event_id"], "chain_id": row["chain_id"],
            "answer_id": row["answer_id"], "event_type": row["event_type"],
            "payload": row["payload"], "created_at": row["created_at"].isoformat(),
            "prev_event_hash": expected,
        }
        actual = hashlib.sha256((expected + _canonical(body)).encode("utf-8")).hexdigest()
        if row["prev_event_hash"] != expected or row["event_hash"] != actual:
            return {"ok": False, "events": len(rows), "broken_at": index, "event_id": row["event_id"]}
        expected = row["event_hash"]
    return {"ok": True, "events": len(rows), "head": expected}


def create_error(event: dict[str, Any]) -> dict[str, Any]:
    with core_connection() as conn:
        conn.execute(
            "INSERT INTO audit_error(error_id,answer_id,error_type,target_id,status,revision_answer_id,payload) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (event["error_id"], event["answer_id"], event["error_type"], event.get("target_id", ""), event["status"], event.get("revision_answer_id", ""), _json(event)),
        )
        conn.execute(
            "INSERT INTO audit_error_event(event_id,error_id,status,payload) VALUES (%s,%s,%s,%s)",
            (f"eev_{uuid.uuid4().hex[:12]}", event["error_id"], event["status"], _json(event)),
        )
    return event


def get_error(error_id: str) -> dict[str, Any] | None:
    with core_connection() as conn:
        row = conn.execute("SELECT payload FROM audit_error WHERE error_id=%s", (error_id,)).fetchone()
    return row["payload"] if row else None


def transition_error(error_id: str, event: dict[str, Any]) -> dict[str, Any]:
    with core_connection() as conn:
        conn.execute(
            "UPDATE audit_error SET status=%s, revision_answer_id=%s, payload=%s, updated_at=now() WHERE error_id=%s",
            (event["status"], event.get("revision_answer_id", ""), _json(event), error_id),
        )
        conn.execute(
            "INSERT INTO audit_error_event(event_id,error_id,status,payload) VALUES (%s,%s,%s,%s)",
            (f"eev_{uuid.uuid4().hex[:12]}", error_id, event["status"], _json(event)),
        )
    return event


def list_errors(limit: int = 100) -> list[dict[str, Any]]:
    with core_connection() as conn:
        rows = conn.execute(
            "SELECT payload FROM audit_error ORDER BY updated_at DESC LIMIT %s",
            (max(1, min(limit, 1000)),),
        ).fetchall()
    return [row["payload"] for row in rows]


def record_reject(
    *,
    answer_id: str,
    action: str,
    target_id: str,
    note: str,
    actor: str,
) -> dict[str, Any]:
    """Write action + error + outbox in one transaction."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    action_event = {
        "action_id": f"act_{uuid.uuid4().hex[:12]}",
        "answer_id": answer_id,
        "action": action,
        "target_id": target_id,
        "note": note[:500],
        "actor": actor,
        "created_at": now,
    }
    error_event = {
        "event": "created",
        "error_id": f"err_{uuid.uuid4().hex[:12]}",
        "answer_id": answer_id,
        "error_type": action,
        "target_id": target_id,
        "severity": "medium",
        "status": "detected",
        "note": note[:500],
        "actor": actor,
        "created_at": now,
        "updated_at": now,
    }
    with core_connection() as conn:
        last = conn.execute(
            "SELECT event_hash FROM audit_event WHERE chain_id=%s ORDER BY created_at DESC, event_id DESC LIMIT 1",
            (answer_id,),
        ).fetchone()
        prev = last["event_hash"] if last else GENESIS
        chain_event = {
            "event_id": f"evt_{uuid.uuid4().hex[:12]}",
            "chain_id": answer_id,
            "answer_id": answer_id,
            "event_type": "action",
            "payload": {"action": action_event, "error": error_event},
            "created_at": now,
            "prev_event_hash": prev,
        }
        chain_event["event_hash"] = hashlib.sha256((prev + _canonical(chain_event)).encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO audit_event(event_id,chain_id,answer_id,event_type,payload,prev_event_hash,event_hash,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (chain_event["event_id"], answer_id, answer_id, "action", _json(chain_event["payload"]), prev, chain_event["event_hash"], now),
        )
        conn.execute(
            "INSERT INTO audit_error(error_id,answer_id,error_type,target_id,status,revision_answer_id,payload) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (error_event["error_id"], answer_id, action, target_id, "detected", "", _json(error_event)),
        )
        conn.execute(
            "INSERT INTO audit_error_event(event_id,error_id,status,payload) VALUES (%s,%s,%s,%s)",
            (f"eev_{uuid.uuid4().hex[:12]}", error_event["error_id"], "detected", _json(error_event)),
        )
        outbox = conn.execute(
            "INSERT INTO audit_outbox(answer_id,error_id,action,payload,idempotency_key) VALUES (%s,%s,%s,%s,%s) RETURNING id,status",
            (answer_id, error_event["error_id"], "regen", _json({"target_id": target_id, "note": note}), action_event["action_id"]),
        ).fetchone()
    return {"action": action_event, "error": error_event, "chain_event": chain_event, "outbox": dict(outbox)}
