"""Optional BO lab routes. Disabled by default; in-memory studies."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request

from plugins.bayes_lab.service import BayesianStudy

STUDIES: dict[str, BayesianStudy] = {}
_LOCK = threading.Lock()
MAX_STUDIES = 32


def _audit(action: str, study_id: str, payload: dict) -> None:
    path = Path(os.environ.get("SCIPAL_BAYES_AUDIT_PATH", "logs/bayes-lab.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"timestamp": time.time(), "action": action, "study_id": study_id, **payload}
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def build_bayes_blueprint() -> Blueprint:
    bp = Blueprint("bayes_lab", __name__, url_prefix="/api/bayes-lab")

    @bp.get("/health")
    def health():
        return jsonify({"ok": True, "plugin": "bayes_lab", "studies": len(STUDIES)})

    @bp.post("/studies")
    def create():
        body = request.get_json(silent=True) or {}
        bounds = body.get("bounds")
        if not isinstance(bounds, list) or not bounds:
            return jsonify({"error": "bounds must be a non-empty list"}), 400
        try:
            study = BayesianStudy(bounds, kappa=float(body.get("kappa") or 2.0))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)[:300]}), 400
        if len(STUDIES) >= MAX_STUDIES:
            return jsonify({"error": "too many studies"}), 429
        study_id = f"bo_{uuid.uuid4().hex[:12]}"
        with _LOCK:
            STUDIES[study_id] = study
        _audit("create", study_id, {"bounds": study.bounds})
        return jsonify({"study_id": study_id, "bounds": study.bounds}), 201

    @bp.post("/studies/<study_id>/observe")
    def observe(study_id: str):
        study = STUDIES.get(study_id)
        if study is None:
            return jsonify({"error": "study not found"}), 404
        body = request.get_json(silent=True) or {}
        try:
            study.observe(list(body.get("point") or []), float(body.get("value")))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)[:300]}), 400
        _audit("observe", study_id, {"point": body.get("point"), "value": body.get("value")})
        return jsonify({"ok": True, "observations": len(study.observations)})

    @bp.post("/studies/<study_id>/suggest")
    def suggest(study_id: str):
        study = STUDIES.get(study_id)
        if study is None:
            return jsonify({"error": "study not found"}), 404
        body = request.get_json(silent=True) or {}
        point = study.suggest(candidates=int(body.get("candidates") or 256))
        _audit("suggest", study_id, {"point": point})
        return jsonify({"point": point})

    return bp
