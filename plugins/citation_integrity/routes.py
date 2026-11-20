"""Citation integrity HTTP routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from plugins.citation_integrity.service import check_reference


def build_citation_integrity_blueprint() -> Blueprint:
    bp = Blueprint("citation_integrity", __name__, url_prefix="/api/citation-integrity")

    @bp.get("/health")
    def health():
        return jsonify({"ok": True, "plugin": "citation_integrity", "version": "0.1.0"})

    @bp.post("/check")
    def check():
        body = request.get_json(silent=True) or {}
        reference = body.get("reference") if isinstance(body.get("reference"), dict) else body
        if not isinstance(reference, dict) or not (reference.get("doi") or reference.get("pmid")):
            return jsonify({"error": "doi or pmid is required"}), 400
        return jsonify(check_reference(reference))

    @bp.post("/check-batch")
    def check_batch():
        body = request.get_json(silent=True) or {}
        references = body.get("references")
        if not isinstance(references, list) or not references:
            return jsonify({"error": "references must be a non-empty list"}), 400
        if len(references) > 20:
            return jsonify({"error": "at most 20 references per batch"}), 400
        results = []
        for index, reference in enumerate(references):
            if not isinstance(reference, dict):
                results.append({"index": index, "status": "unverifiable", "reason": "reference must be an object"})
                continue
            result = check_reference(reference)
            result["index"] = index
            results.append(result)
        return jsonify({"results": results})

    return bp
