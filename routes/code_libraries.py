"""Same-origin proxy for the independent code-rag HTTP service."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flask import Blueprint, jsonify, request, session

from config.settings import DATABASE_PATH
from services.platform.libraries import get_library, set_status
from services.tenancy.service import authorize
from services.tenancy.web import auth_required, resolve_workspace
from code_rag.answer import build_prompt, evidence, extractive_answer, validate_citations
from code_rag.implement import build_prompt as build_implementation_prompt
from code_rag.implement import build_proposal, parse_response, validate_files


def build_code_libraries_blueprint(*, db_path: str = str(DATABASE_PATH), get_llm=None) -> Blueprint:
    bp = Blueprint("code_libraries", __name__)
    db = str(db_path)
    base = os.environ.get("SCIPAL_CODE_API_URL", "http://127.0.0.1:5010").rstrip("/")

    def _workspace() -> str | None:
        return resolve_workspace(default=None, db_path=db)

    def _can(workspace_id: str) -> bool:
        user_id = session.get("user_id")
        if not user_id:
            return not auth_required()
        return authorize(user_id, workspace_id, "read_workspace", db_path=db)

    def _library(library_id: str):
        library = get_library(library_id)
        workspace = _workspace()
        if not library or not workspace or library["workspace_id"] != workspace:
            return None, (jsonify({"error": "library not found"}), 404)
        if library["kind"] != "code":
            return None, (jsonify({"error": "not a code library"}), 400)
        if not _can(workspace):
            return None, (jsonify({"error": "workspace access denied"}), 403)
        return library, None

    def _fetch(method: str, path: str, payload: dict[str, Any] | None = None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        internal = os.environ.get("SCIPAL_INTERNAL_TOKEN", "").strip()
        if internal:
            headers["X-SCIPAL-Internal-Token"] = internal
        workspace = _workspace()
        if workspace:
            headers["X-SCIPAL-Workspace-Id"] = workspace
        request_obj = urllib.request.Request(
            base + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=60) as response:
                return json.loads(response.read().decode("utf-8")), getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return {"error": "code service rejected request", "detail": detail}, 502
        except Exception as exc:  # noqa: BLE001
            return {"error": f"code service unavailable: {exc}"}, 502

    def _call(method: str, path: str, payload: dict[str, Any] | None = None):
        data, status_code = _fetch(method, path, payload)
        return jsonify(data), status_code

    @bp.get("/api/code/libraries")
    def libraries():
        workspace = _workspace()
        if not workspace or not _can(workspace):
            return jsonify({"libraries": []})
        data, status_code = _fetch("GET", "/libraries")
        if status_code != 200:
            return jsonify(data), status_code
        allowed = []
        for item in data.get("libraries", []):
            library = get_library(item.get("library_id", ""))
            if library and library["workspace_id"] == workspace and library["kind"] == "code":
                allowed.append(item)
        return jsonify({"libraries": allowed})

    @bp.get("/api/code/libraries/<library_id>/tree")
    def tree(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        params = urllib.parse.urlencode({
            "path": request.args.get("path") or "",
            "snapshot_id": request.args.get("snapshot_id") or "",
        })
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/tree?{params}")

    @bp.get("/api/code/libraries/<library_id>/environment")
    def environment(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/environment")

    @bp.get("/api/code/libraries/<library_id>/outline")
    def outline(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        params = urllib.parse.urlencode({
            "path": request.args.get("path") or "",
            "snapshot_id": request.args.get("snapshot_id") or "",
        })
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/outline?{params}")

    @bp.get("/api/code/libraries/<library_id>/status")
    def status(library_id: str):
        library, error = _library(library_id)
        if error:
            return error
        data, status_code = _fetch("GET", f"/libraries/{urllib.parse.quote(library_id)}/status")
        if status_code == 200 and (data.get("library") or {}).get("units", 0) > 0:
            if library["status"] != "ready":
                set_status(library_id, "ready")
                data["library"]["status"] = "ready"
        return jsonify(data), status_code

    @bp.post("/api/code/libraries/<library_id>/search")
    def search(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        if not str(body.get("query") or "").strip():
            return jsonify({"error": "query is required"}), 400
        return _call(
            "POST",
            f"/libraries/{urllib.parse.quote(library_id)}/search",
            {
                "query": str(body.get("query")),
                "top_k": int(body.get("top_k") or 10),
                "snapshot_id": str(body.get("snapshot_id") or ""),
                "mode": str(body.get("mode") or ""),
                "language": str(body.get("language") or ""),
                "path_filter": str(body.get("path_filter") or ""),
            },
        )

    @bp.post("/api/code/libraries/<library_id>/feedback")
    def feedback(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        return _call(
            "POST",
            f"/libraries/{urllib.parse.quote(library_id)}/feedback",
            {
                "event_id": str(body.get("event_id") or ""),
                "verdict": str(body.get("verdict") or ""),
                "expected_path": str(body.get("expected_path") or ""),
                "note": str(body.get("note") or ""),
            },
        )

    @bp.post("/api/code/libraries/<library_id>/answer")
    def answer(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        query = str(body.get("query") or "").strip()
        if not query:
            return jsonify({"error": "query is required"}), 400
        data, status_code = _fetch(
            "POST",
            f"/libraries/{urllib.parse.quote(library_id)}/search",
            {"query": query, "top_k": max(1, min(int(body.get("top_k") or 5), 10))},
        )
        if status_code != 200:
            return jsonify(data), status_code
        items = evidence(data.get("hits") or [])
        if not items:
            return jsonify({"answer": "证据不足。", "citations": [], "answer_mode": "refusal"})
        answer_text = extractive_answer(query, items)
        mode = "extractive"
        client = get_llm() if get_llm else None
        if client is not None:
            try:
                system, user = build_prompt(query, items)
                candidate = client.chat(system, user)
                if validate_citations(candidate, items):
                    answer_text = candidate
                    mode = "llm"
            except Exception:  # noqa: BLE001
                pass
        return jsonify({
            "answer": answer_text,
            "citations": items,
            "answer_mode": mode,
        })

    @bp.post("/api/code/libraries/<library_id>/implement")
    def implement(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        task = str(body.get("task") or "").strip()
        if not task:
            return jsonify({"error": "task is required"}), 400
        raw_paths = body.get("target_paths") or []
        if not isinstance(raw_paths, list):
            return jsonify({"error": "target_paths must be a list"}), 400
        target_paths = [str(path) for path in raw_paths if str(path).strip()]
        data, status_code = _fetch(
            "POST",
            f"/libraries/{urllib.parse.quote(library_id)}/search",
            {"query": task, "top_k": max(1, min(int(body.get("top_k") or 5), 10))},
        )
        if status_code != 200:
            return jsonify(data), status_code
        items = evidence(data.get("hits") or [], limit=5)
        if not items:
            return jsonify({"error": "evidence insufficient", "status": "refusal"}), 422
        client = get_llm() if get_llm else None
        if client is None:
            return jsonify({"error": "LLM unavailable", "status": "unavailable"}), 503
        try:
            system, user = build_implementation_prompt(task, target_paths, items)
            candidate = client.chat(system, user)
            parsed = parse_response(candidate)
            proposal = build_proposal(
                task=task,
                data=parsed,
                items=items,
                target_paths=target_paths or None,
            )
            proposal["citations_detail"] = items
            return jsonify(proposal), 200
        except ValueError as exc:
            return jsonify({"error": str(exc)[:500], "status": "rejected"}), 422
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:300], "status": "error"}), 502

    @bp.post("/api/code/libraries/<library_id>/implement/execute")
    def implement_execute(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        if body.get("approve") is not True:
            return jsonify({"error": "explicit approve=true is required"}), 403
        proposal = body.get("proposal")
        if not isinstance(proposal, dict):
            return jsonify({"error": "proposal is required"}), 400
        errors = validate_files(proposal.get("files"))
        if errors:
            return jsonify({"error": "; ".join(errors), "status": "rejected"}), 422
        test_module = str(body.get("test_module") or "").strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", test_module):
            return jsonify({"error": "invalid test_module"}), 400
        sandbox_url = os.environ.get("SCIPAL_SANDBOX_URL", "").rstrip("/")
        token = os.environ.get("SCIPAL_SANDBOX_TOKEN", "").strip()
        if not sandbox_url or not token:
            return jsonify({"error": "sandbox worker is not configured"}), 503
        image = str(body.get("image") or "").strip()
        if not image and os.environ.get("SCIPAL_SANDBOX_USE_LIBRARY_IMAGE", "").strip().lower() in {"1", "true", "yes"}:
            env_data, env_status = _fetch(
                "GET", f"/libraries/{urllib.parse.quote(library_id)}/environment"
            )
            if env_status == 200:
                image = str((env_data.get("environment") or {}).get("runtime_image") or "")
        image = image or "scipal-app:latest"
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?$", image):
            return jsonify({"error": "invalid image"}), 400
        try:
            limit = int(os.environ.get("SCIPAL_SANDBOX_24H_LIMIT", "0") or 0)
        except ValueError:
            limit = 0
        if limit > 0:
            stats, stats_code = _fetch(
                "GET", f"/libraries/{urllib.parse.quote(library_id)}/executions/stats?days=1"
            )
            if stats_code != 200:
                return jsonify({"error": "quota check unavailable"}), 503
            if int(stats.get("executions") or 0) >= limit:
                return jsonify({
                    "error": "sandbox 24h quota exceeded",
                    "limit": limit,
                    "executions": int(stats.get("executions") or 0),
                }), 429
        payload = json.dumps({
            "proposal": proposal,
            "test_module": test_module,
            "timeout": max(1, min(int(body.get("timeout") or 60), 60)),
            "image": image,
        }).encode("utf-8")
        req = urllib.request.Request(
            sandbox_url + "/execute",
            data=payload,
            headers={"Content-Type": "application/json", "X-SCIPAL-Sandbox-Token": token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=75) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return jsonify({"error": "sandbox rejected request", "detail": detail}), exc.code
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"sandbox unavailable: {exc}"}), 502
        execution_id = ""
        try:
            recorded, code = _fetch("POST", f"/libraries/{urllib.parse.quote(library_id)}/executions", {
                "proposal_id": str(proposal.get("proposal_id") or ""),
                "status": str(result.get("status") or ""),
                "exit_code": result.get("exit_code"),
                "duration_seconds": result.get("duration_seconds"),
                "test_module": test_module,
                "image": image,
                "workspace_id": _workspace() or "",
                "error": str(result.get("stderr") or "")[:500] if result.get("status") != "passed" else "",
            })
            if code == 201:
                execution_id = str(recorded.get("execution_id") or "")
        except Exception:  # noqa: BLE001
            pass
        if execution_id:
            result["execution_id"] = execution_id
        return jsonify(result), 200

    @bp.post("/api/code/libraries/<library_id>/executions")
    def execution_create(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        return _call("POST", f"/libraries/{urllib.parse.quote(library_id)}/executions", body)

    @bp.get("/api/code/libraries/<library_id>/executions/stats")
    def execution_stats(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        params = urllib.parse.urlencode({"days": request.args.get("days") or 30})
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/executions/stats?{params}")

    @bp.get("/api/code/libraries/<library_id>/executions")
    def execution_list(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        params = urllib.parse.urlencode({"limit": request.args.get("limit") or 50})
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/executions?{params}")

    @bp.get("/api/code/libraries/<library_id>/context")
    def context(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        params = urllib.parse.urlencode({
            "unit_id": request.args.get("unit_id") or "",
            "max_neighbors": request.args.get("max_neighbors") or 10,
            "direction": request.args.get("direction") or "out",
            "max_tokens": request.args.get("max_tokens") or 4000,
        })
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/context?{params}")

    @bp.get("/api/code/libraries/<library_id>/map")
    def repomap(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        params = urllib.parse.urlencode(
            {
                "snapshot_id": request.args.get("snapshot_id") or "",
                "max_tokens": request.args.get("max_tokens") or 2000,
                "query": request.args.get("query") or "",
            }
        )
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/map?{params}")

    @bp.get("/api/code/libraries/<library_id>/trace")
    def trace(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        unit_id = str(request.args.get("unit_id") or "").strip()
        if not unit_id:
            return jsonify({"error": "unit_id is required"}), 400
        params = urllib.parse.urlencode(
            {
                "unit_id": unit_id,
                "direction": request.args.get("direction") or "both",
                "max_hops": request.args.get("max_hops") or 2,
                "max_nodes": request.args.get("max_nodes") or 30,
            }
        )
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/trace?{params}")

    return bp
