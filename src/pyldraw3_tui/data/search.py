"""In-memory substring search and ranking over the parts catalog.

The whole catalog is already materialized in memory for the category tree
and parts list, so search filters those entries directly instead of adding
an FTS table to the persisted index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ldraw.parts import CatalogEntry, PartsCatalog

_RANK_EXACT_CODE = 0
_RANK_CODE_PREFIX = 1
_RANK_EXACT_DESCRIPTION = 2
_RANK_DESCRIPTION_PREFIX = 3
_RANK_DESCRIPTION_SUBSTRING = 4
_RANK_OTHER = 5


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace runs.

    LDraw descriptions align dimensions with double spaces
    (``Brick  2 x  4``); collapsing them lets natural queries match.
    """
    return " ".join(text.lower().split())


def haystack(entry: CatalogEntry) -> str:
    """Return the lowercased searchable text for a catalog entry."""
    keywords = " ".join(entry.keywords)
    return _normalize(
        f"{entry.code} {entry.description} {entry.category.value} {keywords}",
    )


def _rank(entry: CatalogEntry, query: str) -> int:
    code = entry.code.lower()
    description = _normalize(entry.description)
    if code == query:
        return _RANK_EXACT_CODE
    if code.startswith(query):
        return _RANK_CODE_PREFIX
    if description == query:
        return _RANK_EXACT_DESCRIPTION
    if description.startswith(query):
        return _RANK_DESCRIPTION_PREFIX
    if query in description:
        return _RANK_DESCRIPTION_SUBSTRING
    return _RANK_OTHER


@dataclass(slots=True)
class SearchIndex:
    """Filter and rank catalog entries by substring tokens."""

    entries: tuple[CatalogEntry, ...] = ()
    _haystacks: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_catalog(cls, catalog: PartsCatalog) -> Self:
        """Build an index over every entry in a parts catalog."""
        entries = tuple(catalog.by_code.values())
        return cls(
            entries=entries,
            _haystacks={entry.code: haystack(entry) for entry in entries},
        )

    def _haystack(self, entry: CatalogEntry) -> str:
        cached = self._haystacks.get(entry.code)
        if cached is None:
            cached = haystack(entry)
            self._haystacks[entry.code] = cached
        return cached

    def filter(
        self,
        query: str,
        *,
        within: Iterable[CatalogEntry] | None = None,
    ) -> list[CatalogEntry]:
        """Return entries matching every query token, best matches first.

        An empty query returns the input set unchanged. ``within`` limits
        the search to a subset (e.g. the selected category); by default the
        whole catalog is searched.
        """
        entries = tuple(within) if within is not None else self.entries
        normalized = _normalize(query)
        tokens = normalized.split()
        if not tokens:
            return list(entries)
        matches = [
            entry
            for entry in entries
            if all(token in self._haystack(entry) for token in tokens)
        ]
        matches.sort(key=lambda entry: (_rank(entry, normalized), entry.code))
        return matches
