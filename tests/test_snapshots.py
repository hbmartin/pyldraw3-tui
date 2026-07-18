"""SVG snapshot tests against the fixture library.

A missing baseline is written on first run; set ``SNAPSHOT_UPDATE=1`` to
regenerate after an intentional visual change. (Hand-rolled because
``pytest-textual-snapshot`` pins pytest<9 via syrupy.)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from textual.widgets import TabbedContent

from tests.helpers import wait_for_catalog

if TYPE_CHECKING:
    from pyldraw3_tui.app import PyldrawTuiApp

SNAPSHOT_DIR = Path(__file__).parent / "__snapshots__"
SIZE = (120, 40)


def _check(app: PyldrawTuiApp, name: str) -> None:
    """Compare the app screenshot against the stored baseline."""
    app.clear_notifications()
    svg = app.export_screenshot()
    baseline = SNAPSHOT_DIR / f"{name}.svg"
    if os.environ.get("SNAPSHOT_UPDATE") == "1" or not baseline.exists():
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        baseline.write_text(svg)
        return
    if svg != baseline.read_text():
        (SNAPSHOT_DIR / f"{name}.new.svg").write_text(svg)
        pytest.fail(
            f"snapshot {name!r} changed; inspect {name}.new.svg and rerun "
            "with SNAPSHOT_UPDATE=1 if intentional",
        )


async def test_snapshot_catalog(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await wait_for_catalog(app, pilot)
        _check(app, "catalog")


async def test_snapshot_part_detail_subparts(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await wait_for_catalog(app, pilot)
        app.focus_part_in_catalog("6157")
        app.query_one("#detail-tabs", TabbedContent).active = "tab-subparts"
        await pilot.pause()
        _check(app, "part_detail_subparts")


async def test_snapshot_model_pieces(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=SIZE) as pilot:
        await wait_for_catalog(app, pilot)
        _check(app, "model_pieces")


async def test_snapshot_model_bom(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=SIZE) as pilot:
        await wait_for_catalog(app, pilot)
        app.query_one("#model-tabs", TabbedContent).active = "tab-bom"
        await pilot.pause()
        _check(app, "model_bom")


async def test_snapshot_model_issues(make_app, warnings_ldr):
    app = make_app(model_path=warnings_ldr)
    async with app.run_test(size=SIZE) as pilot:
        await wait_for_catalog(app, pilot)
        app.query_one("#model-tabs", TabbedContent).active = "tab-issues"
        await pilot.pause()
        _check(app, "model_issues")
