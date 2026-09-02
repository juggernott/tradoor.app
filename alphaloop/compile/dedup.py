"""Flags a new spec as a likely-duplicate of a journaled one before it runs.

Exact duplicates are caught by ``StrategySpec.content_hash()`` equality.
"Materially similar" is a softer, human-reviewable signal: high overlap in
universe + features + tags, same kind. This is deliberately not a hard
block — a near-duplicate with one deliberately changed lever is exactly
what ``propose_next_experiments`` recommends, so dedup only warns.
"""

from __future__ import annotations

from dataclasses import dataclass

from alphaloop.core.spec import StrategySpec, SymbolUniverse
from alphaloop.journal.store import JournalEntry


@dataclass
class DedupMatch:
    entry: JournalEntry
    similarity: float
    exact: bool


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _spec_tokens(spec: StrategySpec) -> set[str]:
    tokens = set(spec.features) | set(spec.tags) | {spec.kind}
    if isinstance(spec.universe, SymbolUniverse):
        tokens |= set(spec.universe.symbols)
    return tokens


def find_similar(
    spec: StrategySpec, entries: list[JournalEntry], threshold: float = 0.75
) -> list[DedupMatch]:
    matches = []
    new_hash = spec.content_hash()
    new_tokens = _spec_tokens(spec)
    for entry in entries:
        exact = entry.spec.content_hash() == new_hash
        similarity = 1.0 if exact else _jaccard(new_tokens, _spec_tokens(entry.spec))
        if exact or similarity >= threshold:
            matches.append(DedupMatch(entry=entry, similarity=similarity, exact=exact))
    return sorted(matches, key=lambda m: m.similarity, reverse=True)
