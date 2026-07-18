"""Regenerate the README screenshot gallery.

Drives the app headless against the test fixture library (like the snapshot
tests) and saves one SVG per shot into ``docs/screenshots/`` via
``app.save_screenshot``.

Usage::

    uv run python scripts/make_screenshots.py
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ldraw.config import Config
from textual.widgets import TabbedContent

from pyldraw3_tui.app import PyldrawTuiApp
from pyldraw3_tui.data.source import CatalogSource

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = ROOT / "docs" / "screenshots"
SIZE = (120, 40)


@dataclass(frozen=True)
class Shot:
    """One gallery screenshot: an app state and the file it is saved to."""

    name: str
    model: str | None = None
    prepare: Callable[[PyldrawTuiApp], None] | None = None


def _show_subparts(app: PyldrawTuiApp) -> None:
    app.focus_part_in_catalog("6157")
    app.query_one("#detail-tabs", TabbedContent).active = "tab-subparts"


def _show_summary(app: PyldrawTuiApp) -> None:
    app.query_one("#model-tabs", TabbedContent).active = "tab-summary"


SHOTS = (
    Shot(name="catalog"),
    Shot(name="part-detail", prepare=_show_subparts),
    Shot(name="model-pieces", model="spaceship.mpd"),
    Shot(name="model-summary", model="spaceship.mpd", prepare=_show_summary),
)


async def _capture(shot: Shot, generated_path: Path) -> Path:
    config = Config(
        ldraw_library_path=str(FIXTURES / "library"),
        generated_path=str(generated_path),
    )
    model = FIXTURES / "models" / shot.model if shot.model is not None else None
    app = PyldrawTuiApp(source=CatalogSource(config=config), model_path=model)
    # Deterministic frames (no sliding tab underline), as in the snapshot tests.
    app.animation_level = "none"
    async with app.run_test(size=SIZE) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        if shot.prepare is not None:
            shot.prepare(app)
            await pilot.pause()
        app.clear_notifications()
        await pilot.pause()
        return Path(
            app.save_screenshot(filename=f"{shot.name}.svg", path=str(OUTPUT)),
        )


def main() -> None:
    """Capture every gallery shot into ``docs/screenshots/``."""
    os.environ.pop("NO_COLOR", None)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pyldraw3-tui-shots-") as tmp:
        for shot in SHOTS:
            saved = asyncio.run(_capture(shot=shot, generated_path=Path(tmp)))
            print(f"wrote {saved.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
