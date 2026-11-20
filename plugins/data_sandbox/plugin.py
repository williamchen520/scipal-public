from __future__ import annotations

from config.settings import DATABASE_PATH
from plugins.data_sandbox.routes import build_data_blueprint


def register(ctx):
    return build_data_blueprint(db_path=str(DATABASE_PATH), log=ctx.app.logger)
