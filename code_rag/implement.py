"""Code implementation proposals: generate files, validate, never execute."""

from __future__ import annotations

import ast
import json
import re
import uuid
from pathlib import PurePosixPath
from typing import Any

CITATION = re.compile(r"^E\d+$")
MAX_FILE_BYTES = 200_000
ALLOWED_SUFFIXES = {".py", ".r", ".rmd", ".nf", ".yaml", ".yml", ".toml", ".json", ".md"}


def build_prompt(task: str, target_paths: list[str], items: list[dict[str, Any]]) -> tuple[str, str]:
    blocks = []
    for item in items:
        blocks.append(
            f"[{item['id']}] {item['symbol_name']} {item['path']}:{item['start_line']}-{item['end_line']}\n"
            f"version: {item.get('package_version') or item.get('ref') or 'unknown'}\n"
            f"```\n{item['snippet']}\n```"
        )
    system = (
        "You are a code implementation assistant. Return ONLY a JSON object, no markdown. "
        "Schema: {\"summary\": string, \"files\": [{\"path\": string, \"content\": string}], "
        "\"citations\": [\"E1\"]}. "
        "Use only the supplied evidence for APIs and facts. "
        "If the task is feasible using evidenced APIs, create the requested file(s) even when the target path is new. "
        "Return full file content, no placeholders. Only touch target_paths when provided. "
        "Never claim to have run code. Never include secrets. "
        "The citations array MUST be non-empty whenever files are returned: list every evidence id actually used (for example [\"E1\"]). "
        "Return {\"summary\":\"证据不足\",\"files\":[],\"citations\":[]} only when the evidence is truly insufficient."
    )
    targets = ", ".join(target_paths) if target_paths else "(not restricted)"
    user = f"Task: {task}\nTarget paths: {targets}\n\nEvidence:\n" + "\n\n".join(blocks)
    return system, user


def parse_response(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("response is not a JSON object")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("response must be an object")
    return data


def validate_files(files: Any, target_paths: list[str] | None = None) -> list[str]:
    errors = []
    if not isinstance(files, list) or not files:
        return ["files must be a non-empty list"]
    allowed_targets = set(target_paths or [])
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"files[{index}] must be an object")
            continue
        path = str(item.get("path") or "").strip()
        content = item.get("content")
        if not path:
            errors.append(f"files[{index}].path is required")
            continue
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or not path.endswith(tuple(ALLOWED_SUFFIXES)):
            errors.append(f"unsafe or unsupported path: {path}")
        if allowed_targets and path not in allowed_targets:
            errors.append(f"path not in target_paths: {path}")
        if not isinstance(content, str) or not content.strip():
            errors.append(f"files[{index}].content is empty")
            continue
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            errors.append(f"file too large: {path}")
        if path.endswith(".py"):
            try:
                ast.parse(content)
            except SyntaxError as exc:
                errors.append(f"python syntax error in {path}: {exc.msg}")
    return errors


def build_proposal(
    *,
    task: str,
    data: dict[str, Any],
    items: list[dict[str, Any]],
    target_paths: list[str] | None = None,
) -> dict[str, Any]:
    files = data.get("files")
    errors = validate_files(files, target_paths)
    allowed = {item["id"] for item in items}
    citations = data.get("citations") or []
    if not isinstance(citations, list) or any(str(c) not in allowed for c in citations):
        errors.append("citations must be known evidence ids")
    if items and not citations:
        errors.append("citations must not be empty when evidence is used")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "proposal_id": f"prop_{uuid.uuid4().hex[:16]}",
        "status": "proposed",
        "task": task,
        "summary": str(data.get("summary") or ""),
        "files": files,
        "citations": [str(c) for c in citations],
        "validation": {"ok": True, "errors": []},
        "note": "proposal only; not written, not applied, not executed",
    }
