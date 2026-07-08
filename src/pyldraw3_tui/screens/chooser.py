"""Small modal helpers: an option chooser and a copyable-text fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ChooserScreen(ModalScreen[str | None]):
    """List labelled options; dismisses with the chosen payload (or None)."""

    BINDINGS: ClassVar = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    ChooserScreen {
        align: center middle;
    }
    ChooserScreen > Vertical {
        width: auto;
        max-width: 80%;
        height: auto;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, title: str, options: list[tuple[str, str]]) -> None:
        self._title = title
        self._options = options
        super().__init__()

    def compose(self) -> ComposeResult:
        """Show the title above the option list."""
        with Vertical():
            yield Static(self._title, id="chooser-title")
            yield OptionList(*[label for label, _ in self._options])

    @on(OptionList.OptionSelected)
    def _chosen(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(self._options[event.option_index][1])

    def action_cancel(self) -> None:
        """Dismiss without a choice."""
        self.dismiss(None)


class TextScreen(ModalScreen[None]):
    """Show text for manual copy when no system clipboard is available."""

    BINDINGS: ClassVar = [
        Binding("escape", "dismiss_text", "Close"),
        Binding("enter", "dismiss_text", "Close"),
    ]

    DEFAULT_CSS = """
    TextScreen {
        align: center middle;
    }
    TextScreen > Vertical {
        width: auto;
        max-width: 90%;
        height: auto;
        border: round $warning;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, text: str) -> None:
        self._text = text
        super().__init__()

    def compose(self) -> ComposeResult:
        """Show the uncopyable text with a hint."""
        with Vertical():
            yield Static("Clipboard unavailable — select the text manually:")
            yield Static(self._text, id="fallback-text")

    def action_dismiss_text(self) -> None:
        """Close the modal."""
        self.dismiss(None)
