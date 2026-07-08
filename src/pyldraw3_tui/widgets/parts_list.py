"""Filtered, sortable table of catalog entries."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.widgets import DataTable

from pyldraw3_tui.messages import PartHighlighted

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.parts import CatalogEntry
    from textual.widgets.data_table import ColumnKey


class PartsList(DataTable[str]):
    """Two-column code/description list; the cursor drives the detail pane."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self._entries: dict[str, CatalogEntry] = {}
        self._column_keys: list[ColumnKey] = []
        self._sort_reverse: dict[int, bool] = {}

    def on_mount(self) -> None:
        """Configure columns and row-based cursor."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        self._column_keys = self.add_columns("Code", "Description")

    def set_entries(self, entries: Sequence[CatalogEntry]) -> None:
        """Replace the visible rows and highlight the first one."""
        self.clear()
        self._entries = {entry.code: entry for entry in entries}
        for entry in entries:
            self.add_row(entry.code, entry.description, key=entry.code)
        self.border_title = f"Parts ({len(entries)})"
        if not entries:
            self.post_message(PartHighlighted(None))

    @property
    def highlighted_entry(self) -> CatalogEntry | None:
        """The entry under the cursor, if any."""
        if not self.row_count or self.cursor_row < 0:
            return None
        row_key = self.coordinate_to_cell_key(Coordinate(self.cursor_row, 0)).row_key
        if row_key.value is None:
            return None
        return self._entries.get(row_key.value)

    def focus_code(self, code: str) -> None:
        """Move the cursor to the row for a part code, if present."""
        row_index = self.get_row_index(code)
        self.move_cursor(row=row_index)

    @on(DataTable.RowHighlighted)
    def _highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        code = event.row_key.value if event.row_key is not None else None
        self.post_message(
            PartHighlighted(self._entries.get(code) if code is not None else None),
        )

    @on(DataTable.HeaderSelected)
    def _sort_by_header(self, event: DataTable.HeaderSelected) -> None:
        event.stop()
        self.sort_by(event.column_index)

    def sort_by(self, index: int) -> None:
        """Sort by a column, toggling direction on repeated calls."""
        selected = self.highlighted_entry
        reverse = not self._sort_reverse.get(index, True)
        self._sort_reverse[index] = reverse
        self.sort(self._column_keys[index], reverse=reverse)
        if selected is not None:
            self.focus_code(selected.code)
            self.post_message(PartHighlighted(selected))
