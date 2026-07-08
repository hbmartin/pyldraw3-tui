"""Shared helpers for pilot tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from pyldraw3_tui.app import PyldrawTuiApp


async def wait_for_catalog(app: PyldrawTuiApp, pilot: Pilot) -> None:
    """Block until the catalog-load worker finishes and the UI settles."""
    await app.workers.wait_for_complete()
    await pilot.pause()
