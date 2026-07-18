"""Table of validation issues found in the open model file."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ldraw.validation import Severity
from rich.text import Text
from textual.binding import Binding
from textual.widgets import DataTable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw.validation import ValidationIssue

_SEVERITY_STYLES = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "yellow",
}


class IssuesTable(DataTable[Text | str]):
    """Line number, severity, and message of each validation issue."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def on_mount(self) -> None:
        """Configure columns and row-based cursor."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Line", "Severity", "Message")

    def set_issues(self, issues: Sequence[ValidationIssue]) -> None:
        """Replace rows with the given validation issues."""
        self.clear()
        for issue in issues:
            self.add_row(
                str(issue.line_number),
                Text(
                    issue.severity.value,
                    style=_SEVERITY_STYLES.get(issue.severity, ""),
                ),
                issue.message,
            )
        self.border_title = f"Issues ({len(issues)})"
