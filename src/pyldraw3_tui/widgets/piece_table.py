"""Table of a model's leaf pieces."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable

from pyldraw3_tui.widgets.colour_swatches import colour_chip

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.model import ModelOccurrence
    from ldraw.parts import Parts


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

    def set_occurrences(
        self,
        occurrences: Sequence[ModelOccurrence],
        parts: Parts | None,
    ) -> None:
        """Replace rows with the given flattened model occurrences."""
        self.clear()
        for occurrence in occurrences:
            self.add_row(
                colour_chip(occurrence.colour, parts),
                occurrence.part_code,
                _describe(occurrence.part_code, parts),
                _coordinate(occurrence.position.x),
                _coordinate(occurrence.position.y),
                _coordinate(occurrence.position.z),
                "" if occurrence.step is None else str(occurrence.step),
            )
        self.border_title = f"Pieces ({len(occurrences)})"


def _describe(code: str, parts: Parts | None) -> str:
    if parts is None:
        return ""
    return parts.description_for(code) or ""
