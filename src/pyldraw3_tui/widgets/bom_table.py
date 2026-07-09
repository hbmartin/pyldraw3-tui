"""Bill-of-materials table for the model screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ldraw.colour import Colour
from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable

from pyldraw3_tui.widgets.colour_swatches import colour_chip

if TYPE_CHECKING:
    from ldraw.bom import BomRow
    from ldraw.parts import Parts


class BomTable(DataTable[Text | str | int]):
    """Code, description, colour, and quantity per bill-of-materials row."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self.rows_data: list[BomRow] = []

    def on_mount(self) -> None:
        """Configure columns and row-based cursor."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Code", "Description", "Colour", "Qty")

    def set_rows(self, rows: list[BomRow], parts: Parts | None) -> None:
        """Replace the table contents; keeps rows for CSV/JSON export."""
        self.rows_data = rows
        self.clear()
        for row in rows:
            colour = (
                parts.resolve_colour(row.colour_code)
                if parts is not None and row.colour_code is not None
                else Colour(code=row.colour_code, name=row.colour_name)
            )
            self.add_row(
                row.part,
                row.description or "",
                colour_chip(colour, parts),
                row.quantity,
            )
        self.border_title = f"Bill of materials ({len(rows)} rows)"
