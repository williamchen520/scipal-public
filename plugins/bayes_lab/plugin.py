from __future__ import annotations

from plugins.bayes_lab.routes import build_bayes_blueprint


def register(ctx):
    return build_bayes_blueprint()
