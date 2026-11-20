"""Independent code-rag HTTP service (P5 UI backend).

Run separately from SciPal:
    python -m code_rag.api --port 5010
"""

from __future__ import annotations

import argparse
import hmac
import os
import time

import psycopg
from flask import Flask, jsonify, request

from code_rag.authz import authorize_library
from code_rag.context import build_context
from code_rag.query import parse_query
from code_rag.feedback import record_event, record_feedback
from code_rag.executions import execution_stats, list_executions, record_execution
from code_rag.repomap import build_repomap
from code_rag.service import health
from code_rag.source_link import source_url
from code_rag.trace import trace


def _search(*args, **kwargs):
    mode = str(kwargs.pop("mode", "") or "").lower()
    language = str(kwargs.pop("language", "") or "")
    path_filter = str(kwargs.pop("path_filter", "") or "")
    if mode in {"regex", "symbol"}:
        from code_rag.zoekt import search_zoekt

        return search_zoekt(
            *args, mode=mode, language=language, path_filter=path_filter, **kwargs
        )
    backend = os.environ.get("SCIPAL_CODE_SEARCH_BACKEND", "hybrid").strip().lower()
    if backend == "bm25":
        from code_rag.bm25 import search_bm25

        return search_bm25(*args, **kwargs)
    if backend == "hybrid":
        from code_rag.hybrid import search_hybrid

        return search_hybrid(*args, **kwargs)
    if backend == "bm25_map":
        from code_rag.rerank import search_bm25_map

        return search_bm25_map(*args, **kwargs)
    from code_rag.search import search

    return search(*args, **kwargs)


def create_app() -> Flask:
    app = Flask(__name__)

    @app.before_request
    def _require_internal_token():
        expected = os.environ.get("SCIPAL_INTERNAL_TOKEN", "").strip()
        if not expected:
            return None
        supplied = request.headers.get("X-SCIPAL-Internal-Token", "")
        if not hmac.compare_digest(expected, supplied):
            return jsonify({"error": "unauthorized"}), 401
        library_id = (request.view_args or {}).get("library_id", "")
        if library_id:
            workspace = request.headers.get("X-SCIPAL-Workspace-Id", "").strip()
            required = os.environ.get(
                "SCIPAL_CODE_WORKSPACE_REQUIRED", "0"
            ).strip().lower() in {"1", "true", "yes"}
            if required and not workspace:
                return jsonify({"error": "workspace required"}), 403
            if workspace and not authorize_library(library_id, workspace):
                return jsonify({"error": "library access denied"}), 403
        return None

    def _dsn() -> str:
        return os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")

    @app.get("/health")
    def health_route():
        return jsonify(health())

    @app.get("/libraries/<library_id>/status")
    def status(library_id: str):
        try:
            result = health()
            with psycopg.connect(_dsn()) as conn:
                active = conn.execute(
                    "SELECT snapshot_id FROM code_rag.code_snapshots "
                    "WHERE library_id=%s AND is_active LIMIT 1",
                    (library_id,),
                ).fetchone()
                result["library"] = {
                    "library_id": library_id,
                    "active_snapshot": active[0] if active else "",
                    "snapshots": conn.execute(
                        "SELECT count(*) FROM code_rag.code_snapshots WHERE library_id=%s",
                        (library_id,),
                    ).fetchone()[0],
                    "units": conn.execute(
                        "SELECT count(*) FROM code_rag.code_units WHERE library_id=%s",
                        (library_id,),
                    ).fetchone()[0],
                }
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    def _filter_hits(hits: list[dict], *, language: str = "", path_filter: str = "") -> list[dict]:
        if not language and not path_filter:
            return hits
        extensions = {"python": (".py",), "r": (".r",), "rmd": (".rmd",),
                      "nextflow": (".nf",), "javascript": (".js",), "typescript": (".ts",)}
        allowed = extensions.get(language.lower(), ()) if language else ()
        needle = path_filter.lower()
        return [
            hit for hit in hits
            if (not needle or needle in str(hit.get("path") or "").lower())
            and (not allowed or str(hit.get("path") or "").lower().endswith(allowed))
        ]

    def _enrich_sources(hits: list[dict], library_id: str) -> list[dict]:
        try:
            with psycopg.connect(_dsn()) as conn:
                row = conn.execute(
                    "SELECT s.repo_url, sn.commit_sha, sn.ref, sn.package_version, "
                    "e.environment_id, e.manager, e.base_version FROM code_rag.code_sources s "
                    "JOIN code_rag.code_snapshots sn ON sn.source_id=s.source_id "
                    "LEFT JOIN code_rag.code_environments e ON e.snapshot_id=sn.snapshot_id "
                    "WHERE sn.library_id=%s AND sn.is_active LIMIT 1",
                    (library_id,),
                ).fetchone()
        except Exception:
            row = None
        if not row:
            return hits
        repo_url, commit, ref, package_version, environment_id, manager, base_version = row
        for hit in hits:
            if str(hit.get("unit_type")) == "match":
                continue
            hit["repo_url"] = repo_url
            hit["commit_sha"] = commit
            hit["ref"] = ref or ""
            hit["package_version"] = package_version or ref or ""
            hit["environment_id"] = environment_id or ""
            hit["environment_manager"] = manager or ""
            hit["environment_base_version"] = base_version or ""
            hit["source_url"] = source_url(
                repo_url,
                commit,
                str(hit.get("path") or ""),
                int(hit.get("start_line") or 0),
                int(hit.get("end_line") or 0),
            )
        return hits

    @app.get("/libraries")
    def libraries_route():
        try:
            with psycopg.connect(_dsn()) as conn:
                rows = conn.execute(
                    "SELECT s.library_id,s.repo_url,s.license,sn.snapshot_id,sn.commit_sha,"
                    "(SELECT count(*) FROM code_rag.code_units u WHERE u.library_id=s.library_id "
                    " AND u.snapshot_id=sn.snapshot_id AND u.unit_type <> 'file') AS units,"
                    "(SELECT count(*) FROM code_rag.code_files f WHERE f.library_id=s.library_id "
                    " AND f.snapshot_id=sn.snapshot_id) AS files "
                    "FROM code_rag.code_sources s JOIN code_rag.code_snapshots sn "
                    "ON sn.library_id=s.library_id AND sn.is_active ORDER BY s.library_id"
                ).fetchall()
            return jsonify({"libraries": [
                {"library_id": row[0], "repo_url": row[1], "license": row[2],
                 "snapshot_id": row[3], "commit_sha": row[4], "units": row[5], "files": row[6]}
                for row in rows
            ]})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    def _active_snapshot(conn, library_id: str, snapshot_id: str) -> str:
        if snapshot_id:
            return snapshot_id
        row = conn.execute(
            "SELECT snapshot_id FROM code_rag.code_snapshots WHERE library_id=%s AND is_active LIMIT 1",
            (library_id,),
        ).fetchone()
        return row[0] if row else ""

    @app.get("/libraries/<library_id>/environment")
    def environment_route(library_id: str):
        try:
            with psycopg.connect(_dsn()) as conn:
                row = conn.execute(
                    "SELECT e.environment_id,e.language,e.manager,e.manifest_path,"
                    "e.base_version,e.runtime_image,e.project_name "
                    "FROM code_rag.code_environments e "
                    "JOIN code_rag.code_snapshots sn ON sn.snapshot_id=e.snapshot_id "
                    "WHERE sn.library_id=%s AND sn.is_active LIMIT 1",
                    (library_id,),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:300]}), 500
        if not row:
            return jsonify({"library_id": library_id, "environment": None}), 404
        keys = ("environment_id", "language", "manager", "manifest_path",
                "base_version", "runtime_image", "project_name")
        return jsonify({"library_id": library_id, "environment": dict(zip(keys, row))})

    @app.get("/libraries/<library_id>/tree")
    def tree_route(library_id: str):
        prefix = str(request.args.get("path") or "").strip()
        try:
            with psycopg.connect(_dsn()) as conn:
                snapshot_id = _active_snapshot(
                    conn, library_id, str(request.args.get("snapshot_id") or "")
                )
                if not snapshot_id:
                    return jsonify({"error": "no active snapshot"}), 404
                rows = conn.execute(
                    "SELECT path,language FROM code_rag.code_files "
                    "WHERE library_id=%s AND snapshot_id=%s AND (%s='' OR path LIKE %s) "
                    "ORDER BY path LIMIT 5000",
                    (library_id, snapshot_id, prefix, prefix + "%"),
                ).fetchall()
            return jsonify({"library_id": library_id, "snapshot_id": snapshot_id,
                            "files": [{"path": row[0], "language": row[1]} for row in rows]})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    @app.get("/libraries/<library_id>/outline")
    def outline_route(library_id: str):
        path = str(request.args.get("path") or "").strip()
        if not path:
            return jsonify({"error": "path is required"}), 400
        try:
            with psycopg.connect(_dsn()) as conn:
                snapshot_id = _active_snapshot(
                    conn, library_id, str(request.args.get("snapshot_id") or "")
                )
                if not snapshot_id:
                    return jsonify({"error": "no active snapshot"}), 404
                rows = conn.execute(
                    "SELECT symbol_name,unit_type,start_line,end_line,unit_id "
                    "FROM code_rag.code_symbols WHERE library_id=%s AND snapshot_id=%s AND path=%s "
                    "ORDER BY start_line LIMIT 1000",
                    (library_id, snapshot_id, path),
                ).fetchall()
            return jsonify({"library_id": library_id, "path": path,
                            "symbols": [{"symbol_name": row[0], "unit_type": row[1],
                                         "start_line": row[2], "end_line": row[3], "unit_id": row[4]}
                                        for row in rows]})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    @app.post("/libraries/<library_id>/search")
    def search_route(library_id: str):
        body = request.get_json(silent=True) or {}
        raw_query = str(body.get("query") or "").strip()
        if not raw_query:
            return jsonify({"error": "query is required"}), 400
        parsed = parse_query(raw_query)
        query = parsed.query
        if not query:
            return jsonify({"error": "query is required"}), 400
        try:
            started = time.perf_counter()
            top_k = max(1, min(int(body.get("top_k") or 10), 50))
            mode = str(body.get("mode") or parsed.mode or "")
            language = str(body.get("language") or parsed.language or "")
            path_filter = str(body.get("path_filter") or parsed.path_filter or "")
            hits = _search(
                query,
                library_id=library_id,
                top_k=top_k,
                snapshot_id=str(body.get("snapshot_id") or ""),
                mode=mode,
                language=language,
                path_filter=path_filter,
            )
            hits = _filter_hits(hits, language=language, path_filter=path_filter)
            hits = _enrich_sources(hits, library_id)
            event_id = record_event(
                dsn=_dsn(),
                library_id=library_id,
                query=query,
                mode=mode,
                backend=os.environ.get("SCIPAL_CODE_SEARCH_BACKEND", "hybrid"),
                top_k=top_k,
                latency_ms=(time.perf_counter() - started) * 1000,
                hits=hits,
                workspace_id=request.headers.get("X-SCIPAL-Workspace-Id", ""),
            )
            return jsonify({"query": query, "library_id": library_id, "event_id": event_id, "hits": hits})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    @app.post("/libraries/<library_id>/feedback")
    def feedback_route(library_id: str):
        body = request.get_json(silent=True) or {}
        ok, error = record_feedback(
            dsn=_dsn(),
            library_id=library_id,
            event_id=str(body.get("event_id") or ""),
            verdict=str(body.get("verdict") or ""),
            expected_path=str(body.get("expected_path") or ""),
            note=str(body.get("note") or ""),
        )
        if not ok:
            return jsonify({"error": error}), 400
        return jsonify({"ok": True})

    @app.post("/libraries/<library_id>/executions")
    def execution_create(library_id: str):
        body = request.get_json(silent=True) or {}
        try:
            execution_id = record_execution(
                dsn=_dsn(),
                library_id=library_id,
                proposal_id=str(body.get("proposal_id") or ""),
                status=str(body.get("status") or ""),
                exit_code=body.get("exit_code"),
                duration_seconds=body.get("duration_seconds"),
                test_module=str(body.get("test_module") or ""),
                image=str(body.get("image") or ""),
                workspace_id=str(body.get("workspace_id") or ""),
                error=str(body.get("error") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:500]}), 500
        return jsonify({"execution_id": execution_id}), 201

    @app.get("/libraries/<library_id>/executions/stats")
    def execution_stats_route(library_id: str):
        try:
            days = int(request.args.get("days") or 30)
        except ValueError:
            days = 30
        try:
            return jsonify(execution_stats(dsn=_dsn(), library_id=library_id, days=days))
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:500]}), 500

    @app.get("/libraries/<library_id>/executions")
    def execution_list(library_id: str):
        try:
            limit = int(request.args.get("limit") or 50)
        except ValueError:
            limit = 50
        try:
            rows = list_executions(dsn=_dsn(), library_id=library_id, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:500]}), 500
        return jsonify({"library_id": library_id, "executions": rows})

    @app.get("/libraries/<library_id>/context")
    def context_route(library_id: str):
        unit_id = str(request.args.get("unit_id") or "").strip()
        if not unit_id:
            return jsonify({"error": "unit_id is required"}), 400
        try:
            result = build_context(
                unit_id=unit_id,
                library_id=library_id,
                dsn=_dsn(),
                max_neighbors=max(1, min(int(request.args.get("max_neighbors") or 10), 50)),
                direction=str(request.args.get("direction") or "out"),
                max_tokens=max(200, min(int(request.args.get("max_tokens") or 4000), 20000)),
            )
            unit = dict(result.get("unit") or {})
            unit["unit_type"] = unit.get("unit_type") or "code"
            result["target"] = _enrich_sources([unit], library_id)[0]
            result["source_url"] = result["target"].get("source_url", "")
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    @app.get("/libraries/<library_id>/map")
    def map_route(library_id: str):
        try:
            result = build_repomap(
                library_id=library_id,
                snapshot_id=str(request.args.get("snapshot_id") or ""),
                max_tokens=max(200, min(int(request.args.get("max_tokens") or 2000), 20000)),
                query=str(request.args.get("query") or ""),
                dsn=_dsn(),
            )
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    @app.get("/libraries/<library_id>/trace")
    def trace_route(library_id: str):
        unit_id = str(request.args.get("unit_id") or "").strip()
        if not unit_id:
            return jsonify({"error": "unit_id is required"}), 400
        try:
            result = trace(
                unit_id=unit_id,
                library_id=library_id,
                direction=str(request.args.get("direction") or "both"),
                max_hops=int(request.args.get("max_hops") or 2),
                max_nodes=int(request.args.get("max_nodes") or 30),
            )
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5010)
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
