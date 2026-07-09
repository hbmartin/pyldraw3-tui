"""Unit tests for true-bounds folding in the stats panel."""

from __future__ import annotations

from ldraw.colour import Colour
from ldraw.geometry import Identity, Vector
from ldraw.pieces import Piece

from pyldraw3_tui.widgets.stats_panel import _model_bounds, size_label


def _piece(part: str, x: float = 0, y: float = 0, z: float = 0) -> Piece:
    return Piece(
        colour=Colour(4),
        position=Vector(x, y, z),
        matrix=Identity(),
        part=part,
    )


def test_model_bounds_single_piece(parts):
    bounds = _model_bounds([_piece("3001")], parts)
    assert bounds is not None
    lows, highs = bounds
    assert lows == [-40, -28, -20]
    assert highs == [40, 0, 20]


def test_model_bounds_folds_translated_pieces(parts):
    bounds = _model_bounds([_piece("3001"), _piece("3001", x=100)], parts)
    assert bounds is not None
    lows, highs = bounds
    assert lows == [-40, -28, -20]
    assert highs == [140, 0, 20]


def test_model_bounds_skips_unresolvable_parts(parts):
    assert _model_bounds([_piece("no-such-part")], parts) is None


def test_model_bounds_none_without_parts():
    assert _model_bounds([_piece("3001")], None) is None


def test_size_label_converts_to_mm():
    assert size_label([80, 28, 40]) == "80 x 28 x 40 LDU (32.0 x 11.2 x 16.0 mm)"
