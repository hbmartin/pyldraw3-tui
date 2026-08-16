"""Shared helpers for pilot tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.widgets import Static

from pyldraw3_tui.screens.catalog import CatalogView

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from pyldraw3_tui.app import PyldrawTuiApp


async def wait_for_catalog(app: PyldrawTuiApp, pilot: Pilot) -> None:
    """Block until catalog loading and its initial geometry query settle."""
    async with asyncio.timeout(30):
        while True:
            workers = tuple(app.workers)
            if workers:
                await app.workers.wait_for_complete(workers)
            await pilot.pause()
            view = app.query_one("#catalog-view", expect_type=CatalogView)
            summary = app.query_one("#connection-summary", expect_type=Static)
            summary_text = str(summary.render())
            detail_settled = app.parts is None or (
                view.selected_entry is not None
                and summary_text != "No part selected"
                and not summary_text.startswith("Loading connections for ")
            )
            if not tuple(app.workers) and not view.loading and detail_settled:
                return
