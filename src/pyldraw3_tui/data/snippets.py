"""Build Python snippet strings for a catalog entry.

Pure functions so the export chooser stays trivially testable. The import
snippet mirrors the module/symbol naming that ``pyldraw3`` uses when it
generates the ``ldraw.library.parts.*`` modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ldraw.parts import PartCategory
from ldraw.utils import camel, clean

if TYPE_CHECKING:
    from ldraw.parts import CatalogEntry

DEFAULT_PIECE_COLOUR = 15


def import_snippet(entry: CatalogEntry) -> str | None:
    """Return the generated-library import line, or None for OTHER parts.

    Parts in the OTHER category have no generated module, so there is
    nothing to import.
    """
    symbol = clean(camel(entry.description))
    if entry.minifig_section is not None:
        module = f"ldraw.library.parts.minifig.{entry.minifig_section.value}"
    elif entry.category is not PartCategory.OTHER:
        module = f"ldraw.library.parts.{entry.category.module_name}"
    else:
        return None
    return f"from {module} import {symbol}"


def piece_snippet(entry: CatalogEntry, *, colour: int = DEFAULT_PIECE_COLOUR) -> str:
    """Return a ready-to-paste ``Piece(...)`` placement line."""
    return f'Piece(Colour({colour}), Vector(0, 0, 0), Identity(), "{entry.code}")'


def code_snippet(entry: CatalogEntry) -> str:
    """Return the quoted part code string."""
    return f'"{entry.code}"'
