"""Paper supplementary/import routes."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from routes.papers_actions_context import PaperActionsContext


def register(bp: Blueprint, ctx: PaperActionsContext) -> None:
    @bp.route("/api/papers/<paper_id>/supplementary", methods=["GET"])
    def list_supplementary_files(paper_id):
        """List all supplementary files for a paper."""
        from build_db.db_writer import DatabaseWriter
        writer = DatabaseWriter()
        files = writer.get_supplementary_files(paper_id)
        return jsonify({"supplementary_files": files})


    @bp.route("/api/papers/<paper_id>/supplementary", methods=["POST"])
    def upload_supplementary_file(paper_id):
        """Upload a supplementary file and associate it with a paper.
    
        Request: multipart/form-data with 'file' field and optional 'description'
        """
        import uuid
        from build_db.db_writer import DatabaseWriter

        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        uploaded = request.files['file']
        if not uploaded.filename:
            return jsonify({"error": "Empty filename"}), 400

        # Verify paper exists
        if not ctx.paper_exists(paper_id):
            return jsonify({"error": f"Paper {paper_id} not found"}), 404

        # Save file to documents directory
        original_filename = uploaded.filename
        # Handle duplicate filenames
        save_name = original_filename
        base, ext = os.path.splitext(original_filename)
        counter = 1
        while (ctx.documents_dir / save_name).exists():
            save_name = f"{base}_{counter}{ext}"
            counter += 1

        save_path = ctx.documents_dir / save_name
        uploaded.save(str(save_path))
        file_size = save_path.stat().st_size

        # Determine file type
        file_type = ext.lower().lstrip('.') or 'unknown'

        # Generate supp_id
        supp_id = f"supp_{paper_id}_{uuid.uuid4().hex[:8]}"

        # Get description from form
        description = request.form.get('description', '')

        # Save to database
        writer = DatabaseWriter()
        success = writer.insert_supplementary_file({
            "supp_id": supp_id,
            "paper_id": paper_id,
            "filename": save_name,
            "file_type": file_type,
            "file_path": str(save_path),
            "file_size": file_size,
            "description": description,
        })

        if not success:
            # Clean up file if DB insert failed
            save_path.unlink(missing_ok=True)
            return jsonify({"error": "Failed to save supplementary file record"}), 500

        print(f"ðŸ“Ž Supplementary file added: {save_name} -> {paper_id}")
        return jsonify({
            "success": True,
            "supp_id": supp_id,
            "filename": save_name,
            "file_type": file_type,
            "file_size": file_size,
        })


    @bp.route("/api/papers/<paper_id>/supplementary/<supp_id>/download", methods=["GET"])
    def download_supplementary_file(paper_id, supp_id):
        """Download/serve a supplementary file."""
        from build_db.db_writer import DatabaseWriter
        writer = DatabaseWriter()
        files = writer.get_supplementary_files(paper_id)
        target = next((f for f in files if f["supp_id"] == supp_id), None)
        if not target:
            return jsonify({"error": "Supplementary file not found"}), 404

        file_path = Path(target["file_path"])
        if not file_path.exists():
            return jsonify({"error": f"File missing: {target['filename']}"}), 404

        return send_from_directory(
            str(file_path.parent), file_path.name,
            as_attachment=False)


    @bp.route("/api/papers/<paper_id>/supplementary/<supp_id>", methods=["DELETE"])
    def delete_supplementary_file(paper_id, supp_id):
        """Delete a supplementary file record and optionally the file itself.
    
        Query param: delete_file=1 to also delete the actual file
        """
        from build_db.db_writer import DatabaseWriter
        writer = DatabaseWriter()
        files = writer.get_supplementary_files(paper_id)
        target = next((f for f in files if f["supp_id"] == supp_id), None)
        if not target:
            return jsonify({"error": "Supplementary file not found"}), 404

        # Delete DB record
        success = writer.delete_supplementary_file(supp_id)
        if not success:
            return jsonify({"error": "Failed to delete record"}), 500

        # Optionally delete actual file
        delete_file = request.args.get('delete_file', '0') == '1'
        if delete_file:
            file_path = Path(target["file_path"])
            if file_path.exists():
                file_path.unlink()
                print(f"ðŸ—‘ï¸  Supplementary file deleted: {target['filename']}")

        return jsonify({"success": True, "supp_id": supp_id})


    # ============================================================
    # V25.17: å¯¼å…¥æ–‡çŒ®ï¼ˆæ­£æ–‡ + å¯é€‰è¡¥å……ææ–™ï¼Œä¸€æ¬¡ä¸Šä¼ ï¼‰
    # ============================================================

    @bp.route("/api/papers/import", methods=["POST"])
    def import_paper():
        """å¯¼å…¥ä¸€ç¯‡æ–‡çŒ®ï¼šæ­£æ–‡PDFï¼ˆå¿…é€‰ï¼‰+ è¡¥å……ææ–™ï¼ˆå¯é€‰ï¼Œå¤šé€‰ï¼‰ã€‚

        åªè´Ÿè´£ä¿å­˜æ–‡ä»¶åˆ° documents ç›®å½•ï¼Œä¸è§¦å‘è§£æžã€‚
        å‰ç«¯æ‹¿åˆ° filename åŽå†è°ƒç”¨ /api/papers/parse è§¦å‘è§£æžï¼Œ
        è§£æžå®ŒæˆåŽç”¨ paper_id æŠŠè¡¥å……ææ–™é€ä¸ªå…³è”ã€‚

        Request: multipart/form-data
          - paper: æ­£æ–‡ PDF æ–‡ä»¶ï¼ˆå¿…é€‰ï¼‰
          - supplementary: è¡¥å……ææ–™æ–‡ä»¶ï¼ˆå¯é€‰ï¼Œå¯å¤šä¸ªåŒåå­—æ®µï¼‰
        """
        import uuid

        # æ­£æ–‡ PDFï¼ˆå¿…é€‰ï¼‰
        if 'paper' not in request.files:
            return jsonify({"error": "ç¼ºå°‘æ­£æ–‡ PDF æ–‡ä»¶ï¼ˆpaper å­—æ®µï¼‰"}), 400

        paper_file = request.files['paper']
        if not paper_file.filename:
            return jsonify({"error": "æ­£æ–‡æ–‡ä»¶åä¸ºç©º"}), 400

        # ä¿å­˜æ­£æ–‡ PDFï¼ˆå¤„ç†é‡åï¼‰
        paper_filename = paper_file.filename
        base, ext = os.path.splitext(paper_filename)
        counter = 1
        while (ctx.documents_dir / paper_filename).exists():
            paper_filename = f"{base}_{counter}{ext}"
            counter += 1
        paper_file.save(str(ctx.documents_dir / paper_filename))
        paper_size = (ctx.documents_dir / paper_filename).stat().st_size
        print(f"ðŸ“¥ å¯¼å…¥æ­£æ–‡: {paper_filename} ({paper_size / 1024:.0f} KB)")

        # è¡¥å……ææ–™ï¼ˆå¯é€‰ï¼Œå¤šé€‰ï¼‰
        supp_files = request.files.getlist('supplementary')
        saved_supp = []
        for supp_file in supp_files:
            if not supp_file.filename:
                continue
            # ä¿å­˜è¡¥å……ææ–™ï¼ˆå¤„ç†é‡åï¼‰
            supp_filename = supp_file.filename
            s_base, s_ext = os.path.splitext(supp_filename)
            s_counter = 1
            while (ctx.documents_dir / supp_filename).exists():
                supp_filename = f"{s_base}_{s_counter}{s_ext}"
                s_counter += 1
            supp_file.save(str(ctx.documents_dir / supp_filename))
            supp_size = (ctx.documents_dir / supp_filename).stat().st_size
            file_type = s_ext.lower().lstrip('.') or 'unknown'
            saved_supp.append({
                "filename": supp_filename,
                "original_name": supp_file.filename,
                "file_type": file_type,
                "file_size": supp_size,
            })
            print(f"ðŸ“Ž å¯¼å…¥è¡¥å……ææ–™: {supp_filename} ({supp_size / 1024:.0f} KB)")

        return jsonify({
            "success": True,
            "paper_filename": paper_filename,
            "paper_size": paper_size,
            "supplementary_files": saved_supp,
            "supplementary_count": len(saved_supp),
        })


    @bp.route("/api/papers/<paper_id>/supplementary/link", methods=["POST"])
    def link_supplementary_file(paper_id):
        """å°† documents ç›®å½•ä¸­å·²å­˜åœ¨çš„æ–‡ä»¶å…³è”ä¸ºæŸç¯‡è®ºæ–‡çš„è¡¥å……ææ–™ã€‚
        ç”¨äºŽå¯¼å…¥æµç¨‹ï¼šæ–‡ä»¶å·²é€šè¿‡ /api/papers/import ä¸Šä¼ ï¼Œè§£æžå¾—åˆ° paper_id åŽï¼Œ
        æŒ‰æ–‡ä»¶åç›´æŽ¥å…³è”ï¼Œä¸éœ€è¦é‡æ–°ä¸Šä¼ æ–‡ä»¶å†…å®¹ã€‚

        Request body: {"filename": "xxx.pdf", "description": "..."}
        """
        import uuid
        from build_db.db_writer import DatabaseWriter

        data = request.get_json(force=True)
        filename = data.get('filename', '')
        description = data.get('description', '')

        if not filename:
            return jsonify({"error": "ç¼ºå°‘ filename"}), 400

        # éªŒè¯è®ºæ–‡å­˜åœ¨
        if not ctx.paper_exists(paper_id):
            return jsonify({"error": f"Paper {paper_id} not found"}), 404

        # éªŒè¯æ–‡ä»¶å­˜åœ¨
        file_path = ctx.documents_dir / filename
        if not file_path.exists():
            return jsonify({"error": f"æ–‡ä»¶ä¸å­˜åœ¨: {filename}"}), 404

        file_size = file_path.stat().st_size
        file_type = file_path.suffix.lower().lstrip('.') or 'unknown'
        supp_id = f"supp_{paper_id}_{uuid.uuid4().hex[:8]}"

        writer = DatabaseWriter()
        success = writer.insert_supplementary_file({
            "supp_id": supp_id,
            "paper_id": paper_id,
            "filename": filename,
            "file_type": file_type,
            "file_path": str(file_path),
            "file_size": file_size,
            "description": description,
        })

        if not success:
            return jsonify({"error": "æ•°æ®åº“å†™å…¥å¤±è´¥"}), 500

        print(f"ðŸ”— è¡¥å……ææ–™å…³è”: {filename} -> {paper_id}")
        return jsonify({
            "success": True,
            "supp_id": supp_id,
            "filename": filename,
            "file_type": file_type,
            "file_size": file_size,
        })
