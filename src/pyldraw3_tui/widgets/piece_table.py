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
        self.add_columns("Colour", "Code", "Description", "X", "Y", "Z", "Step")

    def set_pieces(
        self,
        pieces: Sequence[Piece],
        parts: Parts | None,
        step_of: dict[int, int] | None = None,
    ) -> None:
        """Replace rows with the given pieces.

        ``step_of`` maps ``id(piece)`` to its 1-based building step; pieces
        without an entry (e.g. expanded submodel references, whose steps
        belong to their own file) leave the Step cell blank.
        """
        self.clear()
        for piece in pieces:
            step = step_of.get(id(piece)) if step_of is not None else None
            self.add_row(
                colour_chip(piece.colour, parts),
                piece.part,
                _describe(piece.part, parts),
                _coordinate(piece.position.x),
                _coordinate(piece.position.y),
                _coordinate(piece.position.z),
                "" if step is None else str(step),
            )
        self.border_title = f"Pieces ({len(pieces)})"


def _describe(code: str, parts: Parts | None) -> str:
    if parts is None:
        return ""
    return parts.description_for(code) or ""
