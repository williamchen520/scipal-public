"""Build source links from repo metadata."""

from __future__ import annotations

from urllib.parse import quote


def source_url(repo_url: str, commit: str, path: str, start: int = 0, end: int = 0) -> str:
    base = (repo_url or "").strip().rstrip("/")
    if base.endswith(".git"):
        base = base[:-4]
    if not base or not commit or not path:
        return ""
    url = f"{base}/blob/{commit}/{quote(path.lstrip('/'), safe='/')}"
    if start:
        url += f"#L{start}"
        if end and end != start:
            url += f"-L{end}"
    return url
