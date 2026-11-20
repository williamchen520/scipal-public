"""N2: route watch full-text candidates through ImportSession."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from services.imports.orchestrator import process_import
from services.imports.paper_lane import PaperLaneAdapter
from services.imports.session import create_import


def enabled() -> bool:
    return os.environ.get("SCIPAL_WATCH_IMPORT_SESSION", "").strip() == "1"


def stage_jats(
    xml_path: str | Path,
    candidate: dict[str, Any],
    *,
    tenant_id: str = "default",
    library_id: str = "lib_default",
    owner: str = "default",
) -> dict[str, Any]:
    path = Path(xml_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    created = create_import(
        tenant_id=tenant_id,
        library_id=library_id,
        origin="dsh",
        items=[
            {
                "uri": str(candidate.get("doi") or path.name),
                "staged_path": str(path),
                "content_hash": "",
            }
        ],
        created_by=owner,
    )
    result = process_import(
        created["import_id"], paper_adapter=PaperLaneAdapter(build=True)
    )
    item = (result.get("items") or [{}])[0]
    paper_id = (item.get("parsed_json") or {}).get("paper_id")
    if item.get("status") != "built" or not paper_id:
        raise RuntimeError(item.get("error") or "watch ImportSession build failed")
    return {
        "import_id": created["import_id"],
        "paper_id": paper_id,
        "status": item.get("status"),
        "source": str(path),
    }
