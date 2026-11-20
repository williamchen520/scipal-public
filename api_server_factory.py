"""Flask application construction and route registration for SciPal.

Step 1 moved construction/env/bootstrap here. Step 2 moves the auth hook and
blueprint registration here. Lazy getters remain in ``api_server.py`` and are
resolved only when a request calls them, avoiding an import cycle.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from flask import Flask, g, jsonify, request, send_from_directory, session

from services.review.task_manager import task_manager

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


@dataclass(frozen=True)
class AppConfig:
    static_folder: Path = FRONTEND_DIR
    strict_env: bool = True
    bootstrap_tenancy: bool = True
    load_plugins: bool = True


def _api(name: str) -> Callable[..., Any]:
    """Resolve a getter on api_server at request time, not at import time."""

    def resolve(*args: Any, **kwargs: Any) -> Any:
        import api_server

        return getattr(api_server, name)(*args, **kwargs)

    return resolve


def _embed_rows(rows: list[dict[str, Any]]) -> int:
    import api_server

    embedder = api_server.get_embed_rows()
    return embedder(rows) if embedder is not None else 0


def _install_auth_hook(app: Flask) -> None:
    api_token = os.environ.get("SCIPAL_API_TOKEN", "")
    tokens: dict[str, str] = {}
    try:
        import json

        tokens = json.loads(os.environ.get("SCIPAL_API_TOKENS", "{}") or "{}")
    except Exception:
        tokens = {}

    @app.before_request
    def _require_api_token():
        g.owner = os.environ.get("SCIPAL_DEFAULT_OWNER", "default")
        path = request.path
        if not path.startswith("/api/"):
            return None
        if path in ("/api/health", "/api/auth/login"):
            return None
        if path.endswith("/pdf") and request.args.get("token"):
            return None
        if session.get("user_id"):
            return None
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        internal = request.headers.get("X-SCIPAL-Internal-Token", "")
        expected_internal = os.environ.get("SCIPAL_INTERNAL_TOKEN", "").strip()
        if expected_internal and internal == expected_internal:
            g.owner = "internal"
            if not session.get("user_id"):
                session["user_id"] = os.environ.get("SCIPAL_INTERNAL_USER_ID", "")
                session["workspace_id"] = os.environ.get(
                    "SCIPAL_INTERNAL_WORKSPACE_ID", "ws_default"
                )
            return None
        worker = request.headers.get("X-SCIPAL-RAG-Worker-Token", "")
        expected_worker = os.environ.get("SCIPAL_RAG_WORKER_TOKEN", "").strip()
        if expected_worker and worker == expected_worker:
            g.owner = "rag-worker"
            return None
        if tokens:
            owner = tokens.get(token)
            if owner:
                g.owner = owner
                return None
        elif api_token and token == api_token:
            return None
        return jsonify({"error": "unauthorized"}), 401


def _install_static_routes(app: Flask) -> None:
    @app.route("/")
    def index():
        return send_from_directory(str(FRONTEND_DIR), "index.html")

    @app.route("/<path:path>")
    def static_files(path):
        return send_from_directory(str(FRONTEND_DIR), path)


def _register_blueprints(app: Flask) -> None:
    from routes.abstracts import build_abstracts_blueprint
    from routes.audit_queue import build_audit_queue_blueprint
    from routes.claims import build_claims_blueprint
    from routes.code_libraries import build_code_libraries_blueprint
    from routes.core import build_core_blueprint
    from routes.domain_packs import build_domain_packs_blueprint
    from routes.evidence import build_evidence_blueprint
    from routes.experiments import build_experiments_blueprint
    from routes.guard import build_guard_blueprint
    from routes.imports import build_imports_blueprint
    from routes.ingest import build_ingest_blueprint
    from routes.ledger import build_ledger_blueprint
    from routes.libraries import build_libraries_blueprint
    from routes.notes import build_notes_blueprint
    from routes.papers import build_papers_blueprint
    from routes.papers_actions import build_papers_actions_blueprint
    from routes.projects import build_projects_blueprint
    from routes.protocols import build_protocols_blueprint
    from routes.qa import build_qa_blueprint
    from routes.rag_control import build_rag_control_blueprint
    from routes.references import build_references_blueprint
    from routes.review_actions import build_review_actions_blueprint
    from routes.reviews import build_reviews_blueprint
    from routes.runs import build_runs_blueprint
    from routes.search import build_search_blueprint
    from routes.search_downloads import build_search_downloads_blueprint
    from routes.system import build_system_blueprint
    from routes.systematic_review import build_systematic_review_blueprint
    from routes.tasks import build_tasks_blueprint
    from routes.tenancy import build_tenancy_blueprint
    from routes.watch import build_watch_blueprint

    app.register_blueprint(
        build_system_blueprint(db_path=DB_PATH, get_graph=_api("get_graph"), log=app.logger)
    )
    app.register_blueprint(
        build_papers_blueprint(db_path=DB_PATH, get_graph=_api("get_graph"), log=app.logger)
    )
    app.register_blueprint(
        build_search_blueprint(
            get_task_manager=_api("_download_task_manager"),
            log=app.logger,
            get_hybrid_retriever=_api("get_hybrid_retriever"),
            db_path=DB_PATH,
        )
    )
    app.register_blueprint(
        build_abstracts_blueprint(db_path=PROJECT_ROOT / "data" / "abstracts.db")
    )
    app.register_blueprint(
        build_reviews_blueprint(
            db_path=DB_PATH,
            log=app.logger,
            get_task_manager=lambda: task_manager,
            get_review_store=_api("get_review_store"),
            get_llm_client=_api("get_llm_client"),
        )
    )
    app.register_blueprint(
        build_review_actions_blueprint(
            get_task_manager=lambda: task_manager,
            get_llm_client=_api("get_llm_client"),
            get_review_generator=_api("get_review_generator"),
            get_review_store=_api("get_review_store"),
            get_outline_store=_api("get_outline_store"),
            get_retriever=_api("get_retriever"),
            db_path=DB_PATH,
            log=app.logger,
        )
    )
    app.register_blueprint(
        build_core_blueprint(db_path=DB_PATH, get_retriever=_api("get_retriever"))
    )
    app.register_blueprint(
        build_evidence_blueprint(
            db_path=DB_PATH,
            get_retriever=_api("get_evidence_retriever"),
            get_fallback_retriever=_api("get_retriever"),
            log=app.logger,
        )
    )
    app.register_blueprint(build_watch_blueprint(db_path=DB_PATH, log=app.logger))
    app.register_blueprint(
        build_claims_blueprint(
            db_path=DB_PATH,
            log=app.logger,
            get_llm=_api("get_llm_client"),
            get_retriever=_api("get_retriever"),
        )
    )
    app.register_blueprint(build_domain_packs_blueprint(log=app.logger))
    app.register_blueprint(build_tenancy_blueprint(db_path=DB_PATH, log=app.logger))
    app.register_blueprint(build_libraries_blueprint(db_path=str(DB_PATH)))
    app.register_blueprint(
        build_code_libraries_blueprint(db_path=str(DB_PATH), get_llm=_api("get_llm_client"))
    )
    app.register_blueprint(build_rag_control_blueprint())
    app.register_blueprint(build_notes_blueprint(db_path=DB_PATH, log=app.logger))
    app.register_blueprint(build_projects_blueprint(db_path=DB_PATH, log=app.logger))
    app.register_blueprint(build_experiments_blueprint(db_path=DB_PATH, log=app.logger))
    app.register_blueprint(build_runs_blueprint(db_path=DB_PATH, log=app.logger))
    app.register_blueprint(
        build_systematic_review_blueprint(db_path=DB_PATH, log=app.logger)
    )
    app.register_blueprint(
        build_qa_blueprint(
            get_qa_service=_api("get_qa_service"),
            get_retriever=_api("get_retriever"),
            get_task_manager=lambda: task_manager,
            db_path=DB_PATH,
        )
    )
    app.register_blueprint(build_imports_blueprint())
    app.register_blueprint(
        build_papers_actions_blueprint(
            db_path=DB_PATH,
            project_root=PROJECT_ROOT,
            get_task_manager=lambda: task_manager,
            log=app.logger,
        )
    )
    app.register_blueprint(
        build_search_downloads_blueprint(
            db_path=DB_PATH,
            project_root=PROJECT_ROOT,
            get_task_manager=lambda: task_manager,
            log=app.logger,
        )
    )
    if os.environ.get("SCIPAL_INGEST_TRACKING", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        try:
            from plugins.ingest_tracking import build_ingest_tracking_blueprint

            app.register_blueprint(build_ingest_tracking_blueprint(log=app.logger))
        except Exception:
            app.logger.exception("ingest tracking plugin failed to initialize")
    app.register_blueprint(
        build_ingest_blueprint(
            get_service=_api("get_ingest_service"),
            log=app.logger,
            embed_rows=_embed_rows,
        )
    )
    app.register_blueprint(build_guard_blueprint(get_guard=_api("get_guard"), log=app.logger))
    app.register_blueprint(build_audit_queue_blueprint())
    app.register_blueprint(build_ledger_blueprint(get_qa_service=_api("get_qa_service")))
    app.register_blueprint(
        build_references_blueprint(get_library=_api("get_reference_library"), log=app.logger)
    )
    app.register_blueprint(
        build_protocols_blueprint(
            get_service=_api("get_protocol_service"),
            log=app.logger,
            get_review_repo=_api("get_review_repository"),
        )
    )
    app.register_blueprint(
        build_tasks_blueprint(
            list_tasks=_api("_unified_list_tasks"),
            get_task=_api("_unified_get_task"),
            subscribe=_api("_unified_subscribe"),
        )
    )


def create_app(config: AppConfig | None = None) -> Flask:
    config = config or AppConfig()
    app = Flask(
        "api_server",
        static_folder=str(config.static_folder),
        static_url_path="",
    )

    if config.strict_env:
        from services.db.env_guard import check_env

        check_env()

    app.secret_key = os.environ.get("SCIPAL_SECRET_KEY") or os.urandom(32)
    try:
        max_body_mb = max(1, int(os.environ.get("SCIPAL_MAX_CONTENT_LENGTH_MB", "128")))
    except ValueError:
        max_body_mb = 128
    app.config.update(
        MAX_CONTENT_LENGTH=max_body_mb * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SCIPAL_SESSION_COOKIE_SECURE", "0") == "1",
    )

    if config.bootstrap_tenancy:
        from services.tenancy import bootstrap_default_workspace

        try:
            bootstrap_default_workspace(db_path=DB_PATH)
        except Exception:
            app.logger.exception("tenancy bootstrap failed")

    _install_auth_hook(app)
    _register_blueprints(app)
    _install_static_routes(app)

    if config.load_plugins:
        from plugins.registry import load_enabled

        loaded = load_enabled(app)
        if loaded:
            print(f"PLUGINS_LOADED {','.join(loaded)}")
    return app
