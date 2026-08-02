"""Instruction directives active in a selected semantic step."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.instructions import InstructionDirective


class DirectivesTable(DataTable[Text | str]):
    """Source line, semantic kind, parsed data, and lossless raw directive."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def on_mount(self) -> None:
        """Configure columns and row-based cursor."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Line", "Kind", "Data", "Raw LDraw")

    def set_directives(
        self,
        directives: Sequence[InstructionDirective],
    ) -> None:
        """Replace the table with directives from one instruction step."""
        self.clear()
        for directive in directives:
            data = (
                json.dumps(
                    dict(directive.data),
                    sort_keys=True,
                    default=str,
                )
                if directive.data
                else "—"
            )
            self.add_row(
                "—" if directive.source_line is None else str(directive.source_line),
                directive.kind.value,
                data,
                directive.raw.to_ldraw(),
            )
        self.border_title = f"Directives ({len(directives)})"
