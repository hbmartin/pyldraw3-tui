"""Custom Textual messages exchanged between widgets and views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.message import Message

if TYPE_CHECKING:
    from ldraw.parts import (
        CatalogEntry,
        MinifigSection,
        PartCategory,
        PartsCatalog,
    )


@dataclass(frozen=True, slots=True)
class CategoryScope:
    """The catalog subset selected in the category tree.

    Defaults to the whole catalog; at most one of ``category`` /
    ``minifig_section`` / ``minifig_only`` narrows it.
    """

    category: PartCategory | None = None
    minifig_section: MinifigSection | None = None
    minifig_only: bool = False

    def entries(self, catalog: PartsCatalog) -> tuple[CatalogEntry, ...]:
        """Return the catalog entries inside this scope."""
        if self.category is not None:
            return catalog.entries_by_category(self.category)
        if self.minifig_section is not None:
            return catalog.minifig_entries(self.minifig_section)
        if self.minifig_only:
            return catalog.minifig_entries()
        return tuple(catalog.by_code.values())

    @property
    def label(self) -> str:
        """Return a short human-readable name for the scope."""
        if self.category is not None:
            return self.category.value.title()
        if self.minifig_section is not None:
            return f"Minifig · {self.minifig_section.value.title()}"
        if self.minifig_only:
            return "Minifig"
        return "All parts"


class CategorySelected(Message):
    """A category tree node was selected."""

    def __init__(self, scope: CategoryScope) -> None:
        self.scope = scope
        super().__init__()


class PartHighlighted(Message):
    """The cursor landed on a part row (or the list emptied)."""

    def __init__(self, entry: CatalogEntry | None) -> None:
        self.entry = entry
        super().__init__()


class FilterChanged(Message):
    """The live filter text settled after the debounce interval."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__()
