"""Command palette provider: app commands plus global jump-to-part."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, cast

from textual.command import DiscoveryHit, Hit, Provider

if TYPE_CHECKING:
    from collections.abc import Iterator

    from textual.command import Hits

    from pyldraw3_tui.app import PyldrawTuiApp

_MAX_PART_HITS = 15
_PART_HIT_BASE_SCORE = 0.4


class PyldrawTuiCommands(Provider):
    """Palette commands and code/description part lookup."""

    @property
    def _tui(self) -> PyldrawTuiApp:
        return cast("PyldrawTuiApp", self.app)

    def _commands(self) -> Iterator[tuple[str, str, str]]:
        """Yield (name, action, help) triples for the app commands."""
        yield ("Open model…", "open_model_prompt", "Browse a .ldr/.mpd file")
        yield ("Toggle light/dark theme", "toggle_theme", "Switch colour theme")
        yield (
            "Regenerate parts index",
            "regenerate_index",
            "Delete and rebuild the catalog index",
        )
        yield ("Copy part code", "yank_code", "Yank the selected part's code")
        yield (
            "Copy part description or import…",
            "yank_chooser",
            "Yank other part fields",
        )
        yield (
            "Open part on ldraw.org",
            "open_web",
            "Show the selected part in the browser",
        )
        yield (
            "Export Python snippet…",
            "export_snippet",
            "Copy an import, Piece(...), or bare-code snippet",
        )
        yield ("Copy BOM as CSV", "copy_bom_csv", "Yank the model's BOM as CSV")
        yield ("Copy BOM as JSON", "copy_bom_json", "Yank the model's BOM as JSON")
        yield ("Help", "help", "Show the key-binding reference")
        yield ("Quit", "quit", "Exit pyldraw3-tui")

    async def discover(self) -> Hits:
        """List every command when the palette is empty."""
        app = self._tui
        for name, action, help_text in self._commands():
            yield DiscoveryHit(
                name,
                partial(app.run_action, action),
                help=help_text,
            )

    async def search(self, query: str) -> Hits:
        """Match commands by name and catalog parts by code/description."""
        app = self._tui
        matcher = self.matcher(query)
        for name, action, help_text in self._commands():
            if (score := matcher.match(name)) > 0:
                yield Hit(
                    score,
                    matcher.highlight(name),
                    partial(app.run_action, action),
                    help=help_text,
                )
        if app.search_index is None:
            return
        for entry in app.search_index.filter(query)[:_MAX_PART_HITS]:
            text = f"{entry.code} — {entry.description}"
            yield Hit(
                max(matcher.match(text), _PART_HIT_BASE_SCORE),
                matcher.highlight(text),
                partial(app.focus_part_in_catalog, entry.code),
                help="Jump to part in the catalog",
            )
