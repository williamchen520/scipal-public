"""Read and mark the retrieval audit exception queue."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from services.audit.queue import list_events, mark


def build_audit_queue_blueprint() -> Blueprint:
    bp = Blueprint("audit_queue", __name__)

    def _user() -> str:
        return str(session.get("user_id") or "")

    @bp.get("/api/audit/queue")
    def audit_queue():
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        try:
            limit = int(request.args.get("limit") or 100)
        except ValueError:
            limit = 100
        return jsonify({"events": list_events(limit)})

    @bp.post("/api/audit/queue/<queue_id>")
    def audit_mark(queue_id: str):
        if not _user():
            return jsonify({"error": "authentication required"}), 401
        body = request.get_json(silent=True) or {}
        try:
            event = mark(queue_id, str(body.get("status") or ""), str(body.get("note") or ""))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if event is None:
            return jsonify({"error": "queue item not found"}), 404
        return jsonify(event)

    return bp
