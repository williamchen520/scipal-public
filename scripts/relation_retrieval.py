"""Relation-aware retrieval over a directed citation graph.

No sentiment classifier. Channels are structural evidence; ranking uses
reciprocal rank fusion so no hand-tuned channel weights are required.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

Edge = tuple[str, str]  # citing_id -> cited_id


def _ranked(counts: dict[str, int]) -> list[str]:
    return [node for node, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def build_channels(seed: str, edges: Iterable[Edge], *, max_expand: int = 200) -> dict[str, list[str]]:
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for citing, cited in edges:
        if citing != cited:
            outgoing[citing].add(cited)
            incoming[cited].add(citing)

    channels: dict[str, list[str]] = {
        "out_citation": _ranked({node: 1 for node in outgoing.get(seed, set())}),
        "in_citation": _ranked({node: 1 for node in incoming.get(seed, set())}),
    }

    co_citation: dict[str, int] = defaultdict(int)
    for citer in sorted(incoming.get(seed, set()))[:max_expand]:
        for node in outgoing.get(citer, set()):
            if node != seed:
                co_citation[node] += 1
    channels["co_citation"] = _ranked(co_citation)

    coupling: dict[str, int] = defaultdict(int)
    for reference in sorted(outgoing.get(seed, set()))[:max_expand]:
        for citer in sorted(incoming.get(reference, set()))[:max_expand]:
            if citer != seed:
                coupling[citer] += 1
    channels["bibliographic_coupling"] = _ranked(coupling)
    return channels


def rrf(channels: dict[str, list[str]], *, k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in channels.values():
        for rank, node in enumerate(ranking, start=1):
            scores[node] += 1.0 / (k + rank)
    return dict(sorted(scores.items(), key=lambda item: (-item[1], item[0])))


def rank_related(
    seed: str,
    edges: Iterable[Edge],
    *,
    limit: int = 20,
    k: int = 60,
    candidates: Iterable[str] | None = None,
) -> list[dict]:
    channels = build_channels(seed, edges)
    scores = rrf(channels, k=k)
    if candidates is not None:
        for node in candidates:
            scores.setdefault(node, 0.0)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    rows = []
    for node, score in ordered[: max(1, limit)]:
        evidence = {name: node in ranking for name, ranking in channels.items()}
        rows.append({"paper_id": node, "score": round(score, 6), "evidence": evidence})
    return rows


def adjacency(edges: Iterable[Edge]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for citing, cited in edges:
        if citing != cited:
            outgoing[citing].add(cited)
            incoming[cited].add(citing)
    return dict(outgoing), dict(incoming)


def channels_from_adjacency(
    seed: str,
    outgoing: dict[str, set[str]],
    incoming: dict[str, set[str]],
    *,
    max_expand: int = 200,
) -> dict[str, list[str]]:
    channels: dict[str, list[str]] = {
        "out_citation": _ranked({node: 1 for node in outgoing.get(seed, set())}),
        "in_citation": _ranked({node: 1 for node in incoming.get(seed, set())}),
    }
    co_citation: dict[str, int] = defaultdict(int)
    for citer in sorted(incoming.get(seed, set()))[:max_expand]:
        for node in outgoing.get(citer, set()):
            if node != seed:
                co_citation[node] += 1
    channels["co_citation"] = _ranked(co_citation)
    coupling: dict[str, int] = defaultdict(int)
    for reference in sorted(outgoing.get(seed, set()))[:max_expand]:
        for citer in sorted(incoming.get(reference, set()))[:max_expand]:
            if citer != seed:
                coupling[citer] += 1
    channels["bibliographic_coupling"] = _ranked(coupling)
    return channels


def rank_from_adjacency(
    seed: str,
    outgoing: dict[str, set[str]],
    incoming: dict[str, set[str]],
    *,
    limit: int = 20,
    k: int = 60,
    candidates: Iterable[str] | None = None,
    max_expand: int = 200,
) -> list[dict]:
    channels = channels_from_adjacency(seed, outgoing, incoming, max_expand=max_expand)
    scores = rrf(channels, k=k)
    if candidates is not None:
        for node in candidates:
            scores.setdefault(node, 0.0)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    rows = []
    for node, score in ordered[: max(1, limit)]:
        rows.append({
            "paper_id": node,
            "score": round(score, 6),
            "evidence": {name: node in ranking for name, ranking in channels.items()},
        })
    return rows
