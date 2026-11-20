"""Read-only evidence ledger API."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request, session

from services.audit.error_lifecycle import create as create_error, get as get_error, list_errors, transition as transition_error
from services.audit.event_chain import append as append_chain, verify as verify_chain
from services.audit.ledger_revision import revise
from services.audit.ledger_verification import diff_ledgers, verify_ledger
from services.audit.ledger_store import get_ledger, list_ledgers, save
from services.audit.review_actions import list_actions, record


def build_ledger_blueprint(*, get_qa_service=None) -> Blueprint:
    bp = Blueprint("ledger", __name__)

    def _user() -> str:
        return str(session.get("user_id") or "")

    @bp.get("/api/audit/ledgers")
    def ledger_list():
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        try:
            limit = int(request.args.get("limit") or 50)
        except ValueError:
            limit = 50
        return jsonify({"ledgers": list_ledgers(limit)})

    @bp.get("/api/audit/ledgers/<answer_id>")
    def ledger_detail(answer_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        ledger = get_ledger(answer_id)
        if ledger is None:
            return jsonify({"error": "ledger not found"}), 404
        return jsonify(ledger)

    @bp.get("/api/audit/ledgers/<answer_id>/actions")
    def ledger_actions(answer_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        return jsonify({"actions": list_actions(answer_id)})

    @bp.post("/api/audit/ledgers/<answer_id>/rewrite")
    def ledger_rewrite(answer_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        ledger = get_ledger(answer_id)
        if ledger is None:
            return jsonify({"error": "ledger not found"}), 404
        body = request.get_json(silent=True) or {}
        claim_id = str(body.get("claim_id") or "")
        claim = next((row for row in ledger.get("claims") or [] if row.get("claim_id") == claim_id), None)
        if claim is None:
            return jsonify({"error": "claim not found"}), 404
        ids = {str(item) for item in (body.get("evidence_ids") or [])}
        evidence = [ref for ref in ledger.get("evidence") or [] if ref.get("sentence_id") in ids]
        if not evidence:
            return jsonify({"error": "no selected evidence"}), 400
        if get_qa_service is None:
            return jsonify({"error": "LLM service unavailable"}), 503
        try:
            from services.qa.evidence_rewrite import rewrite

            result = rewrite(
                question=str(ledger.get("query") or ""),
                paragraph=str(claim.get("text") or ""),
                evidence=evidence,
                llm=get_qa_service().llm,
                instruction=str(body.get("instruction") or ""),
            )
        except Exception as exc:
            return jsonify({"error": str(exc)[:300]}), 503
        return jsonify(result)

    @bp.post("/api/audit/ledgers/<answer_id>/revisions")
    def ledger_revision(answer_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        ledger = get_ledger(answer_id)
        if ledger is None:
            return jsonify({"error": "ledger not found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            new_ledger = revise(
                ledger,
                action=str(body.get("action") or ""),
                target_id=str(body.get("target_id") or ""),
                note=str(body.get("note") or ""),
                evidence=body.get("evidence"),
                new_text=str(body.get("new_text") or ""),
                evidence_ids=[str(item) for item in (body.get("evidence_ids") or [])],
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        save(new_ledger)
        chain_event = append_chain(
            str(new_ledger.get("chain_id") or new_ledger["answer_id"]),
            "revision",
            {"ledger": new_ledger, "action": str(body.get("action") or "")},
        )
        error = create_error(
            answer_id=answer_id,
            error_type=str(body.get("action") or ""),
            target_id=str(body.get("target_id") or ""),
            note=str(body.get("note") or ""),
            actor=_user(),
            status="repaired",
            revision_answer_id=new_ledger["answer_id"],
            diff=str(body.get("diff") or body.get("note") or ""),
        )
        return jsonify({"ledger": new_ledger, "error": error, "chain_event": chain_event}), 201

    @bp.post("/api/audit/ledgers/<answer_id>/actions")
    def ledger_action(answer_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        ledger = get_ledger(answer_id)
        if ledger is None:
            return jsonify({"error": "ledger not found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            action = str(body.get("action") or "")
            target_id = str(body.get("target_id") or "")
            if action in {"remove_claim", "flag_missing"} and not any(
                row.get("claim_id") == target_id for row in (ledger.get("claims") or [])
            ):
                return jsonify({"error": "claim not found"}), 404
            if os.environ.get("SCIPAL_AUDIT_PG", "").strip().lower() in {"1", "true", "yes", "on"} and action in {"remove_claim", "flag_missing"}:
                from services.audit.pg_store import record_reject

                return jsonify(record_reject(
                    answer_id=answer_id,
                    action=action,
                    target_id=target_id,
                    note=str(body.get("note") or ""),
                    actor=_user(),
                )), 201
            event = record(
                answer_id=answer_id,
                action=action,
                target_id=target_id,
                note=str(body.get("note") or ""),
                actor=_user(),
            )
            error = None
            if action in {"remove_claim", "flag_missing"}:
                error = create_error(
                    answer_id=answer_id,
                    error_type=action,
                    target_id=target_id,
                    note=str(body.get("note") or ""),
                    actor=_user(),
                )
            chain_event = append_chain(
                str(ledger.get("chain_id") or answer_id),
                "action",
                {"action": event, "error": error},
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"action": event, "error": error, "chain_event": chain_event}), 201

    @bp.get("/api/audit/ledgers/<answer_id>/chain")
    def ledger_chain(answer_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        ledger = get_ledger(answer_id)
        if ledger is None:
            return jsonify({"error": "ledger not found"}), 404
        chain_id = str(ledger.get("chain_id") or answer_id)
        return jsonify({"chain_id": chain_id, "verification": verify_chain(chain_id)})

    @bp.get("/api/audit/errors")
    def error_list():
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        return jsonify({"errors": list_errors()})

    @bp.post("/api/audit/errors")
    def error_create():
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        body = request.get_json(silent=True) or {}
        error = create_error(
            answer_id=str(body.get("answer_id") or ""),
            error_type=str(body.get("error_type") or "manual"),
            target_id=str(body.get("target_id") or ""),
            note=str(body.get("note") or ""),
            actor=_user(),
            severity=str(body.get("severity") or "medium"),
        )
        return jsonify(error), 201

    @bp.post("/api/audit/errors/<error_id>/transition")
    def error_transition(error_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        body = request.get_json(silent=True) or {}
        status = str(body.get("status") or "")
        revision_answer_id = str(body.get("revision_answer_id") or "")
        if status == "closed":
            current = get_error(error_id)
            revision = get_ledger(revision_answer_id)
            if current is None:
                return jsonify({"error": "error not found"}), 404
            if revision is None:
                return jsonify({"error": "revision ledger not found"}), 400
            if revision.get("parent_answer_id") != current.get("answer_id"):
                return jsonify({"error": "revision does not belong to this error"}), 400
            verification = verify_ledger(revision)
            if not verification["ok"]:
                return jsonify({"error": "verification failed", "verification": verification}), 400
            diff = diff_ledgers(get_ledger(current.get("answer_id")), revision)
        else:
            verification = {}
            diff = ""
        try:
            event = transition_error(
                error_id,
                status,
                note=str(body.get("note") or ""),
                actor=_user(),
                revision_answer_id=revision_answer_id,
                verification_ok=bool(verification.get("ok")) if status == "closed" else bool(body.get("verification_ok")),
                diff=diff if status == "closed" else str(body.get("diff") or ""),
            )
        except KeyError:
            return jsonify({"error": "error not found"}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(event)

    return bp
