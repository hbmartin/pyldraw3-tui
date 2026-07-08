"""Modal key-binding reference, generated from the app's binding tables."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.table import Table
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

if TYPE_CHECKING:
    from collections.abc import Iterable

    from textual.app import ComposeResult
    from textual.binding import BindingType

BindingSections = list[tuple[str, list[Binding]]]


def _as_binding(binding: BindingType) -> Binding:
    match binding:
        case Binding():
            return binding
        case (key, action):
            return Binding(key, action)
        case (key, action, description):
            return Binding(key, action, description)


def binding_sections(
    sections: Iterable[tuple[str, Iterable[BindingType]]],
) -> BindingSections:
    """Normalize BINDINGS class tables (Binding objects or tuples)."""
    normalized: BindingSections = []
    for title, bindings in sections:
        rows = [_as_binding(binding) for binding in bindings]
        if rows:
            normalized.append((title, rows))
    return normalized


def _render(sections: BindingSections) -> Table:
    table = Table(title="Key bindings", show_header=True, expand=True)
    table.add_column("Key", style="bold", no_wrap=True)
    table.add_column("Action")
    for title, bindings in sections:
        table.add_section()
        table.add_row(f"[dim italic]{title}[/]", "")
        for binding in bindings:
            key = binding.key_display or binding.key
            table.add_row(key, binding.description or binding.action)
    return table


class HelpScreen(ModalScreen[None]):
    """Scrollable key reference; content never drifts from the bindings."""

    BINDINGS: ClassVar = [
        Binding("escape", "dismiss_help", "Close"),
        Binding("question_mark", "dismiss_help", "Close", key_display="?"),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > VerticalScroll {
        width: 70%;
        height: 80%;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, sections: BindingSections) -> None:
        self._sections = sections
        super().__init__()

    def compose(self) -> ComposeResult:
        """Show the generated binding table."""
        with VerticalScroll():
            yield Static(_render(self._sections))

    def action_dismiss_help(self) -> None:
        """Close the modal."""
        self.dismiss(None)
