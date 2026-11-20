"""Shared context for paper action route modules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class PaperActionsContext:
    db_path: Path
    project_root: Path
    documents_dir: Path
    store: Any
    find_parsed_paper: Callable[[str], Any]
    paper_exists: Callable[[str], bool]
    paper_filename: Callable[[str], Any]
    supplementary_counts: Callable[[], dict]
    assign_paper_workspace: Callable[..., None]
    get_task_manager: Callable[[], Any]
    trace_payload: Callable[[str, str], Any] | None = None
