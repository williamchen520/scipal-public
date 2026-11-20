"""Detect and record per-snapshot code environments (metadata only)."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

CANDIDATES = (
    ("pyproject.toml", "pyproject"),
    ("requirements.txt", "pip"),
    ("environment.yml", "conda"),
    ("DESCRIPTION", "renv"),
    ("renv.lock", "renv"),
    ("nextflow.config", "nextflow"),
)


def _stable(*parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8")
    return "env_" + hashlib.sha256(raw).hexdigest()[:24]


def _python_project(path: Path) -> tuple[str, str]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return "", ""
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    return str(project.get("name") or ""), str(project.get("version") or "")


def _r_project(path: Path) -> tuple[str, str]:
    name = version = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("Package:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("Version:"):
            version = line.split(":", 1)[1].strip()
    return name, version


def detect(repo: Path, *, language: str = "", ref: str = "") -> dict:
    for filename, manager in CANDIDATES:
        path = repo / filename
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        base_version = ""
        project_name = ""
        if filename == "pyproject.toml":
            project_name, base_version = _python_project(path)
        elif filename == "DESCRIPTION":
            project_name, base_version = _r_project(path)
        base_version = base_version or ref
        image = {
            "pyproject": "python:3.12",
            "pip": "python:3.12",
            "conda": "python:3.12",
            "renv": "rocker/r-ver",
            "nextflow": "nextflow",
        }.get(manager, "")
        if manager == "renv" and base_version:
            image = f"rocker/r-ver:{base_version}"
        return {
            "environment_id": _stable(str(repo), ref, filename),
            "language": language,
            "manager": manager,
            "manifest_path": filename,
            "manifest_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "project_name": project_name,
            "base_version": base_version,
            "runtime_image": image,
        }
    return {
        "environment_id": _stable(str(repo), ref, ""),
        "language": language,
        "manager": "unknown",
        "manifest_path": "",
        "manifest_hash": "",
        "project_name": "",
        "base_version": ref,
        "runtime_image": "",
    }


def record(conn, *, library_id: str, snapshot_id: str, repo: Path, language: str, ref: str) -> dict:
    item = detect(repo, language=language, ref=ref)
    conn.execute(
        "INSERT INTO code_rag.code_environments "
        "(environment_id,library_id,snapshot_id,language,manager,manifest_path,manifest_hash,"
        "project_name,base_version,runtime_image) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (environment_id) DO UPDATE SET "
        "language=EXCLUDED.language, manager=EXCLUDED.manager, "
        "manifest_path=EXCLUDED.manifest_path, manifest_hash=EXCLUDED.manifest_hash, "
        "project_name=EXCLUDED.project_name, base_version=EXCLUDED.base_version, "
        "runtime_image=EXCLUDED.runtime_image",
        (
            item["environment_id"], library_id, snapshot_id, item["language"],
            item["manager"], item["manifest_path"], item["manifest_hash"],
            item["project_name"], item["base_version"], item["runtime_image"],
        ),
    )
    if item["base_version"]:
        conn.execute(
            "UPDATE code_rag.code_snapshots SET package_version=%s WHERE snapshot_id=%s",
            (item["base_version"], snapshot_id),
        )
    return item
