"""Shared helpers for pilot tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from pyldraw3_tui.app import PyldrawTuiApp


async def wait_for_catalog(app: PyldrawTuiApp, pilot: Pilot) -> None:
    """Block until catalog loading and its initial geometry query settle."""
    await app.workers.wait_for_complete()
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
