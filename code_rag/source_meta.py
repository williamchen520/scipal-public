"""Source hygiene: secret scanning and conservative license detection."""

from __future__ import annotations

import re
from pathlib import Path

SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*"
            r"['\"][A-Za-z0-9_./+=-]{16,}['\"]"
        ),
    ),
)

LICENSES = (
    ("Apache-2.0", re.compile(r"Apache License\s*,?\s*Version 2\.0", re.I)),
    ("MIT", re.compile(r"\bMIT License\b|Permission is hereby granted, free of charge", re.I)),
    ("BSD-3-Clause", re.compile(r"BSD 3-Clause|Redistribution and use in source and binary forms", re.I)),
    ("GPL-3.0", re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 3", re.I)),
    ("GPL-2.0", re.compile(r"GNU GENERAL PUBLIC LICENSE\s+Version 2", re.I)),
    ("MPL-2.0", re.compile(r"Mozilla Public License\s+Version 2\.0", re.I)),
)


def scan_secrets(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                found.append((number, kind))
    return found


def detect_license(repo: Path) -> str:
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "COPYING.txt"):
        path = repo / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:20000]
        except OSError:
            continue
        for identifier, pattern in LICENSES:
            if pattern.search(text):
                return identifier
    return ""


def is_vendored(rel: str) -> bool:
    parts = {part.lower() for part in rel.replace("\\", "/").split("/")}
    return bool(parts & {"vendor", "vendors", "third_party", "third-party", "external", "extern"})


def is_generated(rel: str) -> bool:
    lower = rel.lower()
    return (
        "/generated/" in f"/{lower}"
        or lower.endswith((".min.js", ".min.css", "_pb2.py", ".pb.go", ".g.dart"))
    )
