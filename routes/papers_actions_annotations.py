"""Paper PDF annotation routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.papers import annotations as paper_annotations

from routes.papers_actions_context import PaperActionsContext


def register(bp: Blueprint, ctx: PaperActionsContext) -> None:
    @bp.route("/api/papers/<paper_id>/annotate", methods=["POST"])
    def annotate_pdf(paper_id):
        """æ·»åŠ æˆ–åˆ é™¤ PDF æ³¨é‡Šã€‚æ³¨é‡Šç›´æŽ¥å†™å…¥ PDF æ–‡ä»¶ã€‚

        Request body:
          action: "add" | "delete"
          page: é¡µç ï¼ˆä»Ž1å¼€å§‹ï¼‰
          type: "highlight" | "underline" | "text"
          rect: [x0, y0, x1, y1] PDFæ ‡å‡†åæ ‡ï¼ˆå·¦ä¸‹åŽŸç‚¹ï¼‰
          color: [r, g, b] å¯é€‰ï¼Œ0-1
          text: æ³¨é‡Šæ–‡æœ¬ å¯é€‰
        """
        from services.pdf.annotator import PdfAnnotator

        data = request.get_json(silent=True) or {}
        action = data.get("action", "add")
        page = data.get("page")
        annot_type = data.get("type")
        rect = data.get("rect")
        color = data.get("color")
        text = data.get("text", "")

        if not page or not annot_type or not rect:
            return jsonify({"error": "ç¼ºå°‘å¿…è¦å‚æ•°: page, type, rect"}), 400

        if not ctx.paper_exists(paper_id):
            return jsonify({"error": "paper not found"}), 404

        annotator = PdfAnnotator(str(ctx.db_path), str(ctx.documents_dir))

        if action == "delete":
            result = annotator.delete_annotation(paper_id, page, annot_type, rect, text)
        else:
            result = annotator.add_annotation(paper_id, page, annot_type, rect, color, text)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "æ ‡æ³¨æ“ä½œå¤±è´¥")}), 500

        return jsonify(result)


    # V25.10: åˆ—å‡º PDF ä¸­çš„æ ‡æ³¨
    @bp.route("/api/papers/<paper_id>/annotations", methods=["GET"])
    def list_pdf_annotations(paper_id):
        """åˆ—å‡º PDF ä¸­çš„æ‰€æœ‰æ ‡æ³¨ï¼ˆç”¨äºŽå‰ç«¯æ¸²æŸ“å¯ç‚¹å‡»çš„åˆ é™¤è¦†ç›–å±‚ï¼‰ã€‚

        Query params:
          page: é¡µç ï¼ˆå¯é€‰ï¼Œä¸å¡«åˆ™åˆ—å‡ºæ‰€æœ‰é¡µï¼‰
        """
        if str(request.args.get("scope") or "") == "paper":
            try:
                limit = int(request.args.get("limit") or 200)
            except ValueError:
                limit = 200
            rows = paper_annotations.list_annotations(
                paper_id,
                kind=str(request.args.get("kind") or ""),
                color=str(request.args.get("color") or ""),
                tag=str(request.args.get("tag") or ""),
                limit=limit,
            )
            return jsonify({"annotations": rows, "total": len(rows), "scope": "paper"})

        from services.pdf.annotator import PdfAnnotator

        page = request.args.get("page", type=int)

        if not ctx.paper_exists(paper_id):
            return jsonify({"error": "paper not found"}), 404

        annotator = PdfAnnotator(str(ctx.db_path), str(ctx.documents_dir))
        result = annotator.list_annotations(paper_id, page)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "èŽ·å–æ ‡æ³¨åˆ—è¡¨å¤±è´¥")}), 500

        return jsonify(result)
