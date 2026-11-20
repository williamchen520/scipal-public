"""Paper action route composition."""

from __future__ import annotations

from flask import Blueprint

from routes.papers_actions_context import PaperActionsContext


def register(bp: Blueprint, ctx: PaperActionsContext) -> None:
    from routes.papers_actions_parse import register as register_parse_routes
    from routes.papers_actions_pdf import register as register_pdf_routes
    from routes.papers_actions_supplementary import register as register_supplementary_routes
    from routes.papers_actions_annotations import register as register_annotations_routes
    from routes.papers_actions_trace import register as register_trace_routes

    register_parse_routes(bp, ctx)
    register_pdf_routes(bp, ctx)
    register_supplementary_routes(bp, ctx)
    register_annotations_routes(bp, ctx)
    register_trace_routes(bp, ctx)
