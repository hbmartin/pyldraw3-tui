"""Build Python snippet strings for a catalog entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ldraw.parts import CatalogEntry

DEFAULT_PIECE_COLOUR = 15


def import_snippet(entry: CatalogEntry) -> str | None:
    """Return the generated-library import line, when one exists."""
    return entry.import_statement()


def piece_snippet(entry: CatalogEntry, *, colour: int = DEFAULT_PIECE_COLOUR) -> str:
    """Return a ready-to-paste ``Piece(...)`` placement line."""
    return f'Piece(Colour({colour}), Vector(0, 0, 0), Identity(), "{entry.code}")'


def code_snippet(entry: CatalogEntry) -> str:
    """Return the quoted part code string."""
    return f'"{entry.code}"'
