#!/usr/bin/env python3
"""One task = one git worktree.

Usage:
    python scripts/worktree.py new parser-fix --base dev
    python scripts/worktree.py list
    python scripts/worktree.py remove parser-fix --branch
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKTREES = ROOT / ".worktrees"


def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, text=True, check=check)


def new(name: str, base: str) -> Path:
    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise SystemExit("invalid task name")
    path = WORKTREES / name
    branch = f"task/{name}"
    if path.exists():
        raise SystemExit(f"worktree already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "worktree", "add", "-b", branch, str(path), base])
    print(f"WORKTREE_READY {path} branch={branch}")
    return path


def remove(name: str, delete_branch: bool) -> None:
    path = WORKTREES / name
    branch = f"task/{name}"
    _run(["git", "worktree", "remove", "--force", str(path)], check=False)
    if delete_branch:
        _run(["git", "branch", "-D", branch], check=False)
    print(f"WORKTREE_REMOVED {path} branch_deleted={delete_branch}")


def list_worktrees() -> None:
    result = _run(["git", "worktree", "list", "--porcelain"], check=True)
    print(result.stdout, end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["new", "list", "remove"])
    parser.add_argument("name", nargs="?", default="")
    parser.add_argument("--base", default="dev")
    parser.add_argument("--branch", action="store_true", help="delete task branch on remove")
    args = parser.parse_args()
    if args.action == "new":
        if not args.name:
            parser.error("new requires a task name")
        new(args.name, args.base)
    elif args.action == "remove":
        if not args.name:
            parser.error("remove requires a task name")
        remove(args.name, args.branch)
    else:
        list_worktrees()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
