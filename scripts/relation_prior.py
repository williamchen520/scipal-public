#!/usr/bin/env python3
"""Experimental relation prior for an existing base ranking.

This is a bounded adjustment, not a replacement ranker:

    final = base_norm + min(max_boost, lambda * coverage * recency * stratum * relation_norm)

Recent or low-citation papers receive zero relation weight.
"""

from __future__ import annotations

from typing import Mapping


def _minmax(values: Mapping[str, float]) -> dict[str, float]:
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if high <= low:
        return {key: 0.5 for key in values}
    return {key: (value - low) / (high - low) for key, value in values.items()}


def apply_relation_prior(
    base_scores: Mapping[str, float],
    relation_scores: Mapping[str, float],
    *,
    lam: float = 0.05,
    max_boost: float = 0.10,
    citation_count: Mapping[str, int] | None = None,
    age_days: Mapping[str, int] | None = None,
    min_citations: int = 3,
    min_age_days: int = 180,
    stratum_weight: Mapping[str, float] | None = None,
) -> list[dict]:
    """Return base results adjusted by a bounded, gated relation prior.

    lam=0 is an identity operation. Missing citation/age metadata disables the
    prior for that paper instead of guessing.
    """
    lam = max(0.0, min(float(lam), 1.0))
    base = _minmax(dict(base_scores))
    relation = _minmax(dict(relation_scores))
    counts = citation_count or {}
    ages = age_days or {}
    strata = stratum_weight or {}
    rows = []
    for key, base_norm in base.items():
        coverage = min(1.0, max(0.0, counts.get(key, 0) / min_citations)) if min_citations > 0 else 0.0
        age = ages.get(key)
        recency = 0.0 if age is None or age < min_age_days else 1.0
        stratum = max(0.0, min(1.0, strata.get(key, 1.0)))
        effective = lam * coverage * recency * stratum
        boost = min(max_boost, effective * relation.get(key, 0.0))
        rows.append({
            "paper_id": key,
            "base": round(base_scores[key], 6),
            "relation": round(relation_scores.get(key, 0.0), 6),
            "boost": round(boost, 6),
            "final": round(base_norm + boost, 6),
            "gate": {
                "coverage": round(coverage, 3),
                "recency": recency,
                "stratum": round(stratum, 3),
            },
        })
    return sorted(rows, key=lambda row: (-row["final"], row["paper_id"]))
