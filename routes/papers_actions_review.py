"""Paper review/annotation/enrichment routes.

Extracted from papers_actions.py; endpoint names and URLs must stay stable.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session as flask_session

from services.papers import annotations as paper_annotations
from services.papers import citations as paper_citations
from services.papers import enrich as paper_enrich
from services.papers import external_ids as paper_external_ids
from services.papers import review as paper_review


def register(bp: Blueprint) -> None:
    @bp.get("/api/papers/<paper_id>/review")
    def get_paper_review(paper_id: str):
        try:
            return jsonify(paper_review.get_review(paper_id))
        except paper_review.ReviewError as exc:
            return jsonify({"error": str(exc)}), 404

    @bp.post("/api/papers/<paper_id>/review")
    def post_paper_review(paper_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(
                paper_review.set_decision(
                    paper_id,
                    str(payload.get("decision") or ""),
                    reviewer=str(flask_session.get("username") or flask_session.get("user_id") or "authenticated"),
                    notes=str(payload.get("notes") or ""),
                    force=bool(payload.get("force")),
                )
            )
        except paper_review.ReviewError as exc:
            return jsonify({"error": str(exc)}), 409

    @bp.post("/api/papers/<paper_id>/publish")
    def post_paper_publish(paper_id: str):
        try:
            return jsonify(paper_review.publish(paper_id))
        except paper_review.ReviewError as exc:
            return jsonify({"error": str(exc)}), 409

    @bp.post("/api/papers/<paper_id>/annotations")
    def create_paper_annotation(paper_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            row = paper_annotations.create_annotation(
                paper_id=paper_id,
                para_id=str(payload.get("para_id") or ""),
                sentence_id=str(payload.get("sentence_id") or ""),
                kind=str(payload.get("kind") or "highlight"),
                color=str(payload.get("color") or "yellow"),
                comment=str(payload.get("comment") or ""),
                tags=payload.get("tags"),
                created_by=str(
                    flask_session.get("username")
                    or flask_session.get("user_id")
                    or "authenticated"
                ),
            )
        except paper_annotations.AnnotationNotFound as exc:
            return jsonify({"error": str(exc)}), 404
        except paper_annotations.AnnotationConflict as exc:
            return jsonify({"error": str(exc)}), 409
        except paper_annotations.AnnotationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(row), 201

    @bp.patch("/api/papers/<paper_id>/annotations/<annotation_id>")
    def update_paper_annotation(paper_id: str, annotation_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            row = paper_annotations.update_annotation(
                annotation_id,
                paper_id=paper_id,
                kind=payload.get("kind"),
                color=payload.get("color"),
                comment=payload.get("comment") if "comment" in payload else None,
                tags=payload.get("tags") if "tags" in payload else None,
            )
        except paper_annotations.AnnotationNotFound as exc:
            return jsonify({"error": str(exc)}), 404
        except paper_annotations.AnnotationConflict as exc:
            return jsonify({"error": str(exc)}), 409
        except paper_annotations.AnnotationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(row)

    @bp.delete("/api/papers/<paper_id>/annotations/<annotation_id>")
    def delete_paper_annotation(paper_id: str, annotation_id: str):
        try:
            return jsonify(
                paper_annotations.delete_annotation(
                    annotation_id, paper_id=paper_id
                )
            )
        except paper_annotations.AnnotationNotFound as exc:
            return jsonify({"error": str(exc)}), 404

    @bp.get("/api/papers/<paper_id>/external-ids")
    def get_paper_external_ids(paper_id: str):
        return jsonify(
            {
                "paper_id": paper_id,
                "external_ids": paper_external_ids.list_external_ids(
                    paper_id, source=str(request.args.get("source") or "")
                ),
            }
        )

    @bp.post("/api/papers/<paper_id>/enrich")
    def post_paper_enrich(paper_id: str):
        try:
            return jsonify(paper_enrich.enrich_paper(paper_id))
        except paper_enrich.EnrichError as exc:
            status = 404 if "not found" in str(exc) else 400
            return jsonify({"error": str(exc), "ok": False}), status
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:300], "ok": False}), 502

    @bp.get("/api/papers/<paper_id>/references")
    def get_paper_references(paper_id: str):
        try:
            limit = int(request.args.get("limit") or 200)
        except ValueError:
            limit = 200
        rows = paper_citations.list_references(paper_id, limit=limit)
        return jsonify(
            {
                "paper_id": paper_id,
                "references": rows,
                "total": len(rows),
                "empty_message": "" if rows else "暂无参考文献数据",
            }
        )

    @bp.get("/api/papers/<paper_id>/citations")
    def get_paper_citations(paper_id: str):
        try:
            limit = int(request.args.get("limit") or 200)
        except ValueError:
            limit = 200
        rows = paper_citations.list_citations(paper_id, limit=limit)
        return jsonify(
            {
                "paper_id": paper_id,
                "citations": rows,
                "total": len(rows),
                "empty_message": "" if rows else "暂无引用数据",
            }
        )
