"""Guided first-run screen: download the library and generate the index."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ldraw import generate
from ldraw.downloads import COMPLETE_VERSION, cache_ldraw, download
from textual import on, work
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, LoadingIndicator, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyldraw3_tui.data.source import CatalogSource

_PROBLEM = (
    "No LDraw library was found at the configured location.\n\n"
    "pyldraw3-tui needs the LDraw parts library on disk. The button "
    f"below downloads the {COMPLETE_VERSION!r} release (~80 MB), points "
    "your pyldraw3 configuration at it, and generates the parts index."
)


class SetupScreen(Screen[None]):
    """Shown when ``parts.lst`` is missing; runs download + generate."""

    DEFAULT_CSS = """
    SetupScreen {
        align: center middle;
    }
    SetupScreen > Vertical {
        width: 70;
        height: auto;
        border: round $warning;
        padding: 1 2;
    }
    SetupScreen LoadingIndicator {
        height: 1;
        display: none;
    }
    SetupScreen.working LoadingIndicator {
        display: block;
    }
    """

    def __init__(self, source: CatalogSource) -> None:
        self._source = source
        super().__init__()

    def compose(self) -> ComposeResult:
        """Show the problem statement and the setup action."""
        with Vertical():
            yield Static("[bold]LDraw library not found[/]", id="setup-title")
            yield Static(_PROBLEM, id="setup-problem")
            yield Button(
                "Download & generate",
                variant="primary",
                id="setup-download",
            )
            yield Static("", id="setup-status")
            yield LoadingIndicator()
        yield Footer()

    @on(Button.Pressed, "#setup-download")
    def _start(self, event: Button.Pressed) -> None:
        event.stop()
        event.button.disabled = True
        self.add_class("working")
        self._download_and_generate()

    def _status(self, message: str) -> None:
        self.query_one("#setup-status", Static).update(message)

    @work(thread=True, exclusive=True, group="setup")
    def _download_and_generate(self) -> None:
        """Run the blocking download + generate off the UI thread."""
        app = self.app
        try:
            app.call_from_thread(
                self._status,
                f"Downloading LDraw {COMPLETE_VERSION!r} (~80 MB)…",
            )
            download(show_progress=False)
            config = self._source.config
            config.ldraw_library_path = str(Path(cache_ldraw) / COMPLETE_VERSION)
            config.write()
            app.call_from_thread(
                self._status,
                "Generating library modules and parts index…",
            )
            generate(config=config)
        except (OSError, ValueError) as error:
            app.call_from_thread(self._failed, str(error))
            return
        app.call_from_thread(self._succeeded)

    def _failed(self, reason: str) -> None:
        self.remove_class("working")
        self.query_one("#setup-download", Button).disabled = False
        self._status(f"[red]Setup failed:[/] {reason}")

    def _succeeded(self) -> None:
        self.remove_class("working")
        self._status("Done.")
        self.dismiss(None)
