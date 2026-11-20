"""Paper PDF serving routes."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request, send_from_directory

from routes.papers_actions_context import PaperActionsContext


def register(bp: Blueprint, ctx: PaperActionsContext) -> None:
    @bp.route("/api/papers/<paper_id>/pdf", methods=["GET"])
    def serve_pdf(paper_id):
        """Serve the original PDF file for a paper (for built-in PDF reader)."""
        import sqlite3
        from services.security.signed_url import verify_path

        path = f"/api/papers/{paper_id}/pdf"
        token = request.args.get("token")
        if token:
            if not verify_path(path, token, request.args.get("expires")):
                return jsonify({"error": "invalid or expired token"}), 403
        elif os.environ.get("SCIPAL_REQUIRE_SIGNED_PDF") == "1":
            return jsonify({"error": "signed URL required"}), 403

        row = ctx.paper_filename(paper_id)
        if not row or not row["filename"]:
            return jsonify({"error": "PDF not found"}), 404

        pdf_path = ctx.documents_dir / row["filename"]
        if not pdf_path.exists():
            return jsonify({"error": f"PDF file missing: {row['filename']}"}), 404

        return send_from_directory(
            str(ctx.documents_dir), row["filename"],
            mimetype="application/pdf", conditional=True)
