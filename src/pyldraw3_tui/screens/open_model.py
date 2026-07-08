"""Modal prompt for a model file path (no filesystem picker by design)."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class OpenModelScreen(ModalScreen[str | None]):
    """Ask for a ``.ldr``/``.mpd`` path; dismisses with it (or None)."""

    BINDINGS: ClassVar = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    OpenModelScreen {
        align: center middle;
    }
    OpenModelScreen > Vertical {
        width: 70%;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        """Show the path input."""
        with Vertical():
            yield Static("Open model (.ldr / .mpd) — enter a path:")
            yield Input(placeholder="/path/to/model.ldr", id="model-path-input")

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        value = event.value.strip()
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        """Dismiss without a path."""
        self.dismiss(None)
