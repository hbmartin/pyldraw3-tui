"""Guided first-run screen: download the library and generate the index."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ldraw import ensure_library
from ldraw.downloads import COMPLETE_VERSION
from textual import on, work
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, LoadingIndicator, Static

if TYPE_CHECKING:
    from ldraw import ProgressEvent
    from textual.app import ComposeResult

    from pyldraw3_tui.data.source import CatalogSource

_PROBLEM = (
    "No LDraw library was found at the configured location.\n\n"
    "pyldraw3-tui needs the LDraw parts library on disk. The button "
    f"below downloads the {COMPLETE_VERSION!r} release (~80 MB), points "
    "your pyldraw3 configuration at it, and generates the parts index."
)


def _progress_message(event: ProgressEvent) -> str:
    """Format a pyldraw3 progress event for the single-line status label."""
    if event.total and event.current is not None:
        current = event.current / 1024 / 1024
        total = event.total / 1024 / 1024
        return f"{event.message}: {current:.0f}/{total:.0f} MB"
    if event.path is not None:
        return f"{event.message}: {event.path.name}"
    return event.message


class SetupScreen(Screen[None]):
    """Shown when ``parts.lst`` is missing; runs pyldraw3 setup."""

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
                "Download & prepare",
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
        """Run the blocking setup flow off the UI thread."""
        app = self.app

        def progress(event: ProgressEvent) -> None:
            app.call_from_thread(self._status, _progress_message(event))

        try:
            ensure_library(
                config=self._source.config,
                version=COMPLETE_VERSION,
                write_config=True,
                config_file=self._source.config_file,
                on_progress=progress,
            )
        except Exception as error:  # noqa: BLE001
            reason = str(error) or type(error).__name__
            app.call_from_thread(self._failed, reason)
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
