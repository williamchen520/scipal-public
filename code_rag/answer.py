"""Grounded code answers: evidence package, prompt, citation checks."""

from __future__ import annotations

import re
from typing import Any

CITATION = re.compile(r"\[E(\d+)\]")


def evidence(hits: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    items = []
    for rank, hit in enumerate(hits[: max(1, min(limit, 10))], 1):
        items.append(
            {
                "id": f"E{rank}",
                "unit_id": str(hit.get("unit_id") or ""),
                "symbol_name": str(hit.get("symbol_name") or ""),
                "path": str(hit.get("path") or ""),
                "start_line": int(hit.get("start_line") or 0),
                "end_line": int(hit.get("end_line") or 0),
                "snippet": str(hit.get("snippet") or "")[:1200],
                "source_url": str(hit.get("source_url") or ""),
                "ref": str(hit.get("ref") or ""),
                "package_version": str(hit.get("package_version") or ""),
                "environment_id": str(hit.get("environment_id") or ""),
            }
        )
    return items


def build_prompt(query: str, items: list[dict[str, Any]]) -> tuple[str, str]:
    blocks = []
    for item in items:
        blocks.append(
            f"[{item['id']}] {item['symbol_name']}\n"
            f"path: {item['path']}:{item['start_line']}-{item['end_line']}\n"
            f"```\n{item['snippet']}\n```"
        )
    system = (
        "You answer questions about a codebase using only the supplied evidence. "
        "Cite every factual claim with [E1], [E2], etc. "
        "Do not invent files, symbols, line numbers, or APIs. "
        "If the evidence is insufficient, answer exactly: 证据不足。"
    )
    user = f"Question: {query}\n\nEvidence:\n" + "\n\n".join(blocks)
    return system, user


def extractive_answer(query: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return "证据不足。"
    lines = [f"问题：{query}", "找到以下证据："]
    for item in items:
        lines.append(
            f"[{item['id']}] {item['symbol_name']} — {item['path']}:{item['start_line']}-{item['end_line']}"
        )
    return "\n".join(lines)


def validate_citations(answer: str, items: list[dict[str, Any]]) -> bool:
    if not answer or not items:
        return False
    if "证据不足" in answer:
        return True
    ids = CITATION.findall(answer)
    if not ids:
        return False
    allowed = {item["id"][1:] for item in items}
    return all(value in allowed for value in ids)
