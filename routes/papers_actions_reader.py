"""Paper reading/native/analysis routes.

Extracted from papers_actions.py; endpoint names and URLs must stay stable.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.papers.analysis import analyze_paper
from services.papers.bindings import bind_link, list_bindings
from services.papers.code_links import extract_and_store, list_links, manual_link, validate_link
from services.papers.evidence import paper_evidence
from services.papers.federation import federated_paper
from services.papers.flow import paper_data_flow
from services.papers.html_native import html_native
from services.papers.jats import jats_native
from services.papers.modules import paper_modules
from services.papers.pdf_native import pdf_native
from services.papers.reader import paper_first_paragraph, paper_outline, paper_paragraphs, paragraph_sentences
from services.papers.replication import replication_plan
from services.papers.sections import paper_section
from services.papers.sources import list_sources


def register(bp: Blueprint) -> None:
    @bp.route("/api/papers/<paper_id>/outline", methods=["GET"])
    def get_paper_outline(paper_id):
        sections = paper_outline(paper_id)
        if not sections:
            return jsonify({"error": "Paper not found or empty"}), 404
        return jsonify({"paper_id": paper_id, "sections": sections})

    @bp.route("/api/papers/<paper_id>/paragraphs", methods=["GET"])
    def get_paper_paragraphs(paper_id):
        try:
            offset = int(request.args.get("offset", 0))
            limit = int(request.args.get("limit", 50))
        except ValueError:
            return jsonify({"error": "offset/limit must be integers"}), 400
        section = request.args.get("section", "")
        include_captions = request.args.get("include_captions", "0").lower() in {"1", "true", "yes"}
        rows = paper_paragraphs(
            paper_id,
            section=section,
            offset=offset,
            limit=limit,
            include_captions=include_captions,
        )
        return jsonify({"paper_id": paper_id, "section": section, "paragraphs": rows})

    @bp.route("/api/papers/<paper_id>/paragraphs/first", methods=["GET"])
    def get_paper_first_paragraph(paper_id):
        section = request.args.get("section", "")
        include_captions = request.args.get("include_captions", "0").lower() in {"1", "true", "yes"}
        row = paper_first_paragraph(paper_id, section=section, include_captions=include_captions)
        if not row:
            return jsonify({"error": "Paragraph not found", "section": section}), 404
        return jsonify({"paper_id": paper_id, "section": section, "paragraph": row})

    @bp.route("/api/papers/<paper_id>/paragraphs/<para_id>/sentences", methods=["GET"])
    def get_paragraph_sentences(paper_id, para_id):
        rows = paragraph_sentences(paper_id, para_id)
        if not rows:
            return jsonify({"error": "Sentence tree not found", "para_id": para_id}), 404
        return jsonify({"paper_id": paper_id, "para_id": para_id, "sentences": rows})

    @bp.route("/api/papers/<paper_id>/code-links", methods=["GET"])
    def get_paper_code_links(paper_id):
        return jsonify({"paper_id": paper_id, "links": list_links(paper_id)})

    @bp.route("/api/papers/<paper_id>/code-links/extract", methods=["POST"])
    def extract_paper_code_links(paper_id):
        return jsonify(extract_and_store(paper_id))

    @bp.route("/api/papers/<paper_id>/code-links", methods=["POST"])
    def add_paper_code_link(paper_id):
        payload = request.get_json(silent=True) or {}
        url = str(payload.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400
        try:
            link = manual_link(
                paper_id,
                url,
                license_value=str(payload.get("license") or ""),
                commit_sha=str(payload.get("commit") or ""),
                status=str(payload.get("status") or "candidate"),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"paper_id": paper_id, "link": link}), 201

    @bp.route("/api/papers/<paper_id>/code-links/<link_id>/validate", methods=["POST"])
    def validate_paper_code_link(paper_id, link_id):
        try:
            result = validate_link(paper_id, link_id)
        except KeyError:
            return jsonify({"error": "Link not found"}), 404
        status = 200 if result.get("status") == "validated" else 422
        return jsonify(result), status

    @bp.route("/api/papers/<paper_id>/code-libraries", methods=["GET"])
    def get_paper_code_libraries(paper_id):
        return jsonify({"paper_id": paper_id, "bindings": list_bindings(paper_id)})

    @bp.route("/api/papers/<paper_id>/code-links/<link_id>/bind", methods=["POST"])
    def bind_paper_code_link(paper_id, link_id):
        payload = request.get_json(silent=True) or {}
        library_id = str(payload.get("library_id") or "").strip()
        if not library_id:
            return jsonify({"error": "library_id is required"}), 400
        try:
            binding = bind_link(
                paper_id,
                link_id,
                library_id=library_id,
                snapshot_id=str(payload.get("snapshot_id") or ""),
                parser_supported=bool(payload.get("parser_supported")),
                reason=str(payload.get("reason") or ""),
            )
        except KeyError:
            return jsonify({"error": "Link not found"}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 409
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 503
        return jsonify({"paper_id": paper_id, "binding": binding}), 201

    @bp.route("/api/papers/<paper_id>/data-flow", methods=["GET"])
    def get_paper_data_flow(paper_id):
        return jsonify(paper_data_flow(paper_id))

    @bp.route("/api/papers/<paper_id>/modules", methods=["GET"])
    def get_paper_modules(paper_id):
        return jsonify(paper_modules(paper_id))

    @bp.route("/api/papers/<paper_id>/replication-plan", methods=["POST"])
    def build_replication_plan(paper_id):
        payload = request.get_json(silent=True) or {}
        target = str(payload.get("target") or "").strip()
        if not target:
            return jsonify({"error": "target is required"}), 400
        try:
            result = replication_plan(paper_id, target)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        status = 409 if result.get("status") == "blocked" else 200
        return jsonify(result), status

    @bp.route("/api/papers/<paper_id>/sections/<section_type>", methods=["GET"])
    def get_paper_section(paper_id, section_type):
        include_paragraphs = request.args.get("include_paragraphs", "0").lower() in {"1", "true", "yes"}
        try:
            limit = int(request.args.get("limit", 50))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            return jsonify({"error": "limit/offset must be integers"}), 400
        try:
            result = paper_section(
                paper_id,
                section_type,
                include_paragraphs=include_paragraphs,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        status = 404 if result.get("status") == "not_found" else 200
        return jsonify(result), status

    @bp.route("/api/papers/<paper_id>/federated", methods=["GET"])
    def get_paper_federated(paper_id):
        raw = request.args.get("source_kind", "")
        kinds = [part.strip() for part in raw.split(",") if part.strip()]
        result = federated_paper(paper_id, source_kinds=kinds)
        if not result:
            return jsonify({"paper_id": paper_id, "status": "not_indexed"}), 404
        return jsonify(result)

    @bp.route("/api/papers/<paper_id>/html", methods=["GET"])
    def get_paper_html(paper_id):
        include = request.args.get("include_paragraphs", "0").lower() in {"1", "true", "yes"}
        native = html_native(paper_id, include_paragraphs=include)
        if not native:
            return jsonify({"paper_id": paper_id, "status": "not_indexed"}), 404
        return jsonify(native)

    @bp.route("/api/papers/<paper_id>/pdf-native", methods=["GET"])
    def get_paper_pdf_native(paper_id):
        include = request.args.get("include_paragraphs", "0").lower() in {"1", "true", "yes"}
        native = pdf_native(paper_id, include_paragraphs=include)
        if not native:
            return jsonify({"paper_id": paper_id, "status": "not_indexed"}), 404
        return jsonify(native)

    @bp.route("/api/papers/<paper_id>/jats", methods=["GET"])
    def get_paper_jats(paper_id):
        native = jats_native(paper_id)
        if not native:
            return jsonify({"paper_id": paper_id, "status": "not_indexed"}), 404
        return jsonify(native)

    @bp.route("/api/papers/<paper_id>/sources", methods=["GET"])
    def get_paper_sources(paper_id):
        return jsonify({"paper_id": paper_id, "sources": list_sources(paper_id)})

    @bp.route("/api/papers/<paper_id>/analysis", methods=["GET"])
    def get_paper_analysis(paper_id):
        query = request.args.get("q", "").strip()
        try:
            top_k = int(request.args.get("top_k", 8))
        except ValueError:
            return jsonify({"error": "top_k must be an integer"}), 400
        compact = request.args.get("compact", "0").lower() in {"1", "true", "yes"}
        include_sections = request.args.get("include_sections", "0").lower() in {"1", "true", "yes"}
        result = analyze_paper(
            paper_id,
            query=query,
            top_k=top_k,
            compact=compact,
            include_sections=include_sections,
        )
        if not result:
            return jsonify({"error": "Paper not found"}), 404
        return jsonify(result)

    @bp.route("/api/papers/<paper_id>/evidence", methods=["POST"])
    def get_paper_evidence(paper_id):
        payload = request.get_json(silent=True) or {}
        query = str(payload.get("query") or "").strip()
        if not query:
            return jsonify({"error": "query is required"}), 400
        try:
            top_k = int(payload.get("top_k", 8))
        except (TypeError, ValueError):
            return jsonify({"error": "top_k must be an integer"}), 400
        rows = paper_evidence(paper_id, query, top_k=top_k)
        return jsonify({"paper_id": paper_id, "query": query, "evidence": rows})
