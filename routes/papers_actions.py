"""Papers routes: local scan / parse / pdf / supplementary / import / annotations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from services.tenancy.web import resolve_workspace
from services.papers.paper_store import PaperStore


_PARSED_PAPER_ORDER = (
    "ORDER BY (total_paragraphs IS NULL) ASC, total_paragraphs DESC"
)


def _papers_pg_enabled() -> bool:
    return os.environ.get("SCIPAL_PAPERS_READ_BACKEND", "").strip().lower() in {
        "postgres", "postgresql", "pg", "1", "true"
    }


def _find_parsed_paper(filename: str, conn=None):
    override = globals().get("_lookup_override")
    if override is not None:
        return override(filename)
    from services.papers.lookup import find_parsed_paper

    return find_parsed_paper(filename)


def build_papers_actions_blueprint(
    *,
    db_path: Path,
    project_root: Path,
    get_task_manager: Callable[[], Any],
    log: Any,
    lookup: Callable[[str], Any] | None = None,
    paper_store: Any = None,
    trace_payload: Callable[[str, str], Any] | None = None,
) -> Blueprint:
    bp = Blueprint("papers_actions", __name__)
    from routes.papers_actions_review import register as register_paper_review_routes
    from routes.papers_actions_reader import register as register_paper_reader_routes

    register_paper_review_routes(bp)
    register_paper_reader_routes(bp)

    globals()["db_path_for_lookup"] = lambda: db_path
    globals()["DOCUMENTS_DIR"] = project_root / "documents"
    globals()["_lookup_override"] = lookup
    store = paper_store or PaperStore(db_path)

    def _paper_exists(paper_id: str) -> bool:
        return bool(store.exists(paper_id))

    def _paper_filename(paper_id: str):
        return store.filename(paper_id)

    @bp.before_request
    def scope_paper_routes():
        paper_id = (request.view_args or {}).get("paper_id")
        if not paper_id:
            return None
        workspace_id = resolve_workspace(db_path=db_path)
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 401
        if not store.in_workspace(paper_id, workspace_id):
            return jsonify({"error": "Paper not found"}), 404
        return None


    def assign_paper_workspace(paper_id: str, workspace_id: str | None = None) -> None:
        workspace_id = workspace_id or resolve_workspace(db_path=db_path)
        if workspace_id:
            store.assign_workspace(paper_id, workspace_id)

    def _supplementary_counts() -> dict:
        return store.supplementary_counts()

    from routes.papers_actions_context import PaperActionsContext
    from routes.papers_actions_local import register as register_paper_local_routes

    paper_ctx = PaperActionsContext(
        db_path=db_path,
        project_root=project_root,
        documents_dir=project_root / "documents",
        store=store,
        find_parsed_paper=_find_parsed_paper,
        paper_exists=_paper_exists,
        paper_filename=_paper_filename,
        supplementary_counts=_supplementary_counts,
        assign_paper_workspace=assign_paper_workspace,
        get_task_manager=get_task_manager,
        trace_payload=trace_payload,
    )
    register_paper_local_routes(bp, paper_ctx)

    # ---------------------------------------------------------------------------
    # Frontend
    # ---------------------------------------------------------------------------


    return bp

