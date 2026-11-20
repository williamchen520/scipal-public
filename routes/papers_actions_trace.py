"""Paper sentence trace routes."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from routes.papers_actions_context import PaperActionsContext


def register(bp: Blueprint, ctx: PaperActionsContext) -> None:
    def _trace_payload_pg(paper_id: str, sentence_id: str):
        from services.security.signed_url import sign_path
        from services.db.pg_pool import main_read_connection

        pg = main_read_connection()
        try:
            row = pg.execute(
                "SELECT s.sentence_id, s.text, s.page, s.bbox, s.section_id, "
                "       p.filename, p.title "
                "FROM sentences s JOIN papers p ON p.paper_id = s.paper_id "
                "WHERE s.paper_id = %s AND s.sentence_id = %s",
                (paper_id, sentence_id),
            ).fetchone()
            if not row:
                return None
            section_path = []
            current = row["section_id"]
            seen = set()
            while current and current not in seen:
                seen.add(current)
                section = pg.execute(
                    "SELECT title, parent_id FROM sections WHERE section_id = %s",
                    (current,),
                ).fetchone()
                if not section:
                    break
                section_path.append(section["title"])
                current = section["parent_id"]
            section_path.reverse()

            links = []
            for link in pg.execute(
                "SELECT target_type, target_id, relation, source, confidence, page, bbox "
                "FROM sentence_links WHERE sentence_id = %s",
                (sentence_id,),
            ):
                item = dict(link)
                if item["target_type"] == "citation":
                    detail = pg.execute(
                        "SELECT raw_text, doi, title FROM citations WHERE citation_id = %s",
                        (item["target_id"],),
                    ).fetchone()
                elif item["target_type"] == "figure":
                    detail = pg.execute(
                        "SELECT fig_number, caption, page, bbox FROM figures WHERE fig_id = %s",
                        (item["target_id"],),
                    ).fetchone()
                else:
                    detail = pg.execute(
                        "SELECT table_number, caption FROM tables WHERE table_id = %s",
                        (item["target_id"],),
                    ).fetchone()
                item["detail"] = dict(detail) if detail else {}
                links.append(item)

            return {
                "paper_id": paper_id,
                "title": row["title"],
                "sentence_id": sentence_id,
                "sentence": row["text"],
                "page": row["page"],
                "bbox": row["bbox"],
                "section_path": section_path,
                "links": links,
                "pdf_url": sign_path(f"/api/papers/{paper_id}/pdf"),
                "pdf_url_unsigned": f"/api/papers/{paper_id}/pdf",
                "image_url": f"/api/papers/{paper_id}/trace.png?sentence_id={sentence_id}",
            }
        finally:
            pg.close()

    def _trace_payload(paper_id: str, sentence_id: str):
        if ctx.trace_payload is not None:
            return ctx.trace_payload(paper_id, sentence_id)
        return _trace_payload_pg(paper_id, sentence_id)

    @bp.route("/api/papers/<paper_id>/trace", methods=["GET"])
    def sentence_trace(paper_id):
        sentence_id = request.args.get("sentence_id", "")
        if not sentence_id:
            return jsonify({"error": "缺少 sentence_id 参数"}), 400
        payload = _trace_payload(paper_id, sentence_id)
        if payload is None:
            return jsonify({"error": "sentence not found"}), 404
        return jsonify(payload)

    @bp.route("/api/papers/<paper_id>/trace.png", methods=["GET"])
    def sentence_trace_image(paper_id):
        sentence_id = request.args.get("sentence_id", "")
        if not sentence_id:
            return jsonify({"error": "缺少 sentence_id 参数"}), 400
        payload = _trace_payload(paper_id, sentence_id)
        if payload is None:
            return jsonify({"error": "sentence not found"}), 404
        if not payload.get("bbox") or not payload.get("page"):
            return jsonify({"error": "该句子没有 bbox（XML 或扫描件）"}), 404
        filename_row = ctx.paper_filename(paper_id)
        pdf_path = ctx.documents_dir / (filename_row["filename"] if filename_row else "")
        if not pdf_path.exists():
            return jsonify({"error": "PDF not found"}), 404
        try:
            import fitz

            with fitz.open(str(pdf_path)) as doc:
                page = doc[int(payload["page"]) - 1]
                x0, y0, x1, y1 = [
                    float(v) for v in str(payload["bbox"]).split(",")
                ]
                pad = 6
                clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
                clip &= page.rect
                pixmap = page.get_pixmap(clip=clip, dpi=200)
                return Response(pixmap.tobytes("png"), mimetype="image/png")
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"渲染失败: {str(exc)[:120]}"}), 500
