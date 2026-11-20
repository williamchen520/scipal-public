"""Convert exported bad-case feedback into eval cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def language_for(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".py"):
        return "python"
    if lower.endswith(".r"):
        return "r"
    if lower.endswith(".rmd"):
        return "rmd"
    if lower.endswith(".nf"):
        return "nextflow"
    if lower.endswith(".js"):
        return "javascript"
    if lower.endswith(".ts"):
        return "typescript"
    return ""


def convert(items: list[dict]) -> list[dict]:
    cases = []
    seen = set()
    for item in items:
        expected = str(item.get("expected_path") or "").strip()
        query = str(item.get("query") or "").strip()
        library = str(item.get("library_id") or "").strip()
        if not expected or not query or not library:
            continue
        key = (library, query, expected)
        if key in seen:
            continue
        seen.add(key)
        cases.append(
            {
                "id": f"feedback_{item.get('event_id', '')[:12]}",
                "library_id": library,
                "language": language_for(expected),
                "category": "feedback",
                "query": query,
                "expected_symbol": "",
                "expected_path": expected,
            }
        )
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="eval/code_rag_stack/feedback_bad_cases.json")
    parser.add_argument("--output", default="eval/code_rag_stack/feedback_cases.json")
    args = parser.parse_args()
    items = json.loads(Path(args.input).read_text(encoding="utf-8"))
    cases = convert(items)
    Path(args.output).write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FEEDBACK_CASES_OK cases={len(cases)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
