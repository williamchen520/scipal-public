"""Stable API exposed to plugins. Core internals stay behind this module."""

from __future__ import annotations

from services.db.pg_pool import pg_connection

__all__ = ["pg_connection"]
