"""Evidence-constrained paragraph rewrite. The LLM may only cite selected evidence."""

from __future__ import annotations

import re
from typing import Any

CITE_RE = re.compile(r"\[P(\d+)\]")
SYSTEM = (
    "You rewrite scientific text using ONLY the numbered evidence supplied. "
    "Every factual sentence must cite [P#]. Do not add outside facts. "
    "If evidence is insufficient, say so explicitly."
)


def build_prompt(*, question: str, paragraph: str, evidence: list[dict[str, Any]], instruction: str = "") -> str:
    lines = [f"QUESTION:\n{question}", "", "EVIDENCE:"]
    for index, item in enumerate(evidence, 1):
        lines.append(f"[P{index}] {item.get('text') or ''}")
    lines.extend([
        "",
        "ORIGINAL PARAGRAPH:",
        paragraph,
        "",
        f"INSTRUCTION: {instruction or 'Rewrite only the parts not supported by the selected evidence.'}",
        "",
        "Return the rewritten paragraph with [P#] citations.",
    ])
    return "\n".join(lines)


def rewrite(
    *,
    question: str,
    paragraph: str,
    evidence: list[dict[str, Any]],
    llm: Any,
    instruction: str = "",
) -> dict[str, Any]:
    if not evidence:
        return {
            "status": "rejected",
            "reason": "no_evidence",
            "draft": "",
            "used_sentence_ids": [],
            "unknown_labels": [],
        }
    draft = llm.chat(SYSTEM, build_prompt(
        question=question, paragraph=paragraph, evidence=evidence, instruction=instruction
    ), temperature=0.1)
    labels = sorted({int(match.group(1)) for match in CITE_RE.finditer(draft or "")})
    unknown = [f"[P{label}]" for label in labels if label < 1 or label > len(evidence)]
    used = [
        evidence[label - 1].get("sentence_id", "")
        for label in labels
        if 1 <= label <= len(evidence)
    ]
    return {
        "status": "rejected" if unknown or not (draft or "").strip() else "draft",
        "reason": "out_of_scope_evidence" if unknown else "",
        "draft": draft or "",
        "used_sentence_ids": [sid for sid in used if sid],
        "unknown_labels": unknown,
        "evidence_count": len(evidence),
    }
