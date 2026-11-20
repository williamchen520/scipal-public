"""Rotate a SciPal tenant user's password without printing the old hash."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.tenancy.service import hash_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="ui_admin")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    password = args.password or os.environ.get("SCIPAL_NEW_ADMIN_PASSWORD", "").strip()
    generated = False
    if not password:
        password = secrets.token_urlsafe(24)
        generated = True

    from services.db.pg_pool import auth_connection

    conn = auth_connection()
    try:
        row = conn.execute(
            "UPDATE users SET password_hash=%s WHERE username=%s RETURNING user_id",
            (hash_password(password), args.username),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if not row:
        print(f"user not found: {args.username}", file=sys.stderr)
        return 1
    print(f"rotated user={args.username} user_id={row['user_id']}")
    if generated:
        print(f"new_password={password}")
        print("store it in the deployment secret manager, not in git")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
