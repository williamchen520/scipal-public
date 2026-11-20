from __future__ import annotations

from plugins.citation_integrity.routes import build_citation_integrity_blueprint


def register(ctx):
    return build_citation_integrity_blueprint()
