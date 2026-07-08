"""Table of a model's leaf pieces."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable

from pyldraw3_tui.widgets.colour_swatches import colour_chip

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.parts import Parts
    from ldraw.pieces import Piece


def _coordinate(value: float) -> str:
    return f"{value:g}"


class PieceTable(DataTable[Text | str]):
    """Colour swatch, code, description, and origin of each piece."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def on_mount(self) -> None:
        """Configure columns and row-based cursor."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Colour", "Code", "Description", "X", "Y", "Z")

    def set_pieces(self, pieces: Sequence[Piece], parts: Parts | None) -> None:
        """Replace rows with the given pieces."""
        self.clear()
        for piece in pieces:
            self.add_row(
                colour_chip(piece.colour, parts),
                piece.part,
                _describe(piece.part, parts),
                _coordinate(piece.position.x),
                _coordinate(piece.position.y),
                _coordinate(piece.position.z),
            )
        self.border_title = f"Pieces ({len(pieces)})"


def _describe(code: str, parts: Parts | None) -> str:
    if parts is None:
        return ""
    return parts.by_code.get(code) or parts.by_code.get(code.lower()) or ""
