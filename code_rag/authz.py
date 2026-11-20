"""Workspace authorization for code libraries (defense in depth)."""

from __future__ import annotations

import os
from typing import Optional

import psycopg


def _core_dsn() -> str:
    return (
        os.environ.get("SCIPAL_CORE_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def library_workspace(library_id: str) -> Optional[str]:
    dsn = _core_dsn()
    if not dsn:
        return None
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT workspace_id FROM libraries "
            "WHERE library_id=%s AND status <> 'deleted'",
            (library_id,),
        ).fetchone()
    return row[0] if row else None


def authorize_library(library_id: str, workspace_id: str) -> bool:
    if not workspace_id:
        return False
    return library_workspace(library_id) == workspace_id
