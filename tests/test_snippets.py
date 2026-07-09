"""Unit tests for the Python snippet builders."""

from __future__ import annotations

from ldraw.parts import CatalogEntry, MinifigSection, PartCategory

from pyldraw3_tui.data.snippets import code_snippet, import_snippet, piece_snippet


def test_import_snippet_for_category():
    e = CatalogEntry(
        code="3001", description="Brick 2 x 4", category=PartCategory.BRICK
    )
    assert import_snippet(e) == "from ldraw.library.parts.bricks import Brick2X4"


def test_import_snippet_for_minifig_section():
    e = CatalogEntry(
        code="973",
        description="Minifig Torso",
        category=PartCategory.MINIFIG,
        minifig_section=MinifigSection.TORSOS,
    )
    assert import_snippet(e) == "from ldraw.library.parts.minifig.torsos import Torso"


def test_import_snippet_none_for_other_category():
    e = CatalogEntry(code="x1", description="Oddball", category=PartCategory.OTHER)
    assert import_snippet(e) is None


def test_piece_snippet_default_colour():
    e = CatalogEntry(
        code="3001", description="Brick 2 x 4", category=PartCategory.BRICK
    )
    assert piece_snippet(e) == 'Piece(Colour(15), Vector(0, 0, 0), Identity(), "3001")'


def test_piece_snippet_custom_colour():
    e = CatalogEntry(
        code="3022", description="Plate 2 x 2", category=PartCategory.PLATE
    )
    assert (
        piece_snippet(e, colour=4)
        == 'Piece(Colour(4), Vector(0, 0, 0), Identity(), "3022")'
    )


def test_code_snippet():
    e = CatalogEntry(
        code="3001", description="Brick 2 x 4", category=PartCategory.BRICK
    )
    assert code_snippet(e) == '"3001"'


def test_import_matches_cli_suggestion(parts):
    """The import snippet must agree with pyldraw3's own CLI suggestion."""
    from ldraw.cli import _suggested_import

    for entry in parts.catalog.by_code.values():
        assert import_snippet(entry) is not None
        assert _suggested_import(entry) == import_snippet(entry)
