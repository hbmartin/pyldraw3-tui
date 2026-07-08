"""Pilot interaction tests for the catalog screen."""

from __future__ import annotations

import asyncio
import threading
from typing import Never

import pytest
from ldraw.parts import MinifigSection, PartCategory

import pyldraw3_tui.app as app_module
from pyldraw3_tui.data.source import CatalogSource, SourceState
from pyldraw3_tui.messages import CategoryScope, PartHighlighted
from pyldraw3_tui.screens.catalog import CatalogView
from pyldraw3_tui.screens.chooser import ChooserScreen
from pyldraw3_tui.screens.help import HelpScreen
from pyldraw3_tui.widgets.filter_box import FilterBox
from pyldraw3_tui.widgets.part_detail import _metadata_text
from pyldraw3_tui.widgets.parts_list import PartsList
from pyldraw3_tui.widgets.subpart_tree import SubPartTree
from tests.helpers import wait_for_catalog


class BlockingCatalogSource(CatalogSource):
    """Catalog source that blocks the first load until a test releases it."""

    def __init__(self, *, config, catalog_db, release) -> None:
        super().__init__(config=config)
        self._catalog_db = catalog_db
        self.release = release
        self.started = threading.Event()
        self.load_calls = 0

    @property
    def catalog_db(self):
        """Return the marker index path controlled by the test."""
        return self._catalog_db

    def classify(self):
        """Classify only from the marker index path."""
        if not self.parts_lst_path.is_file():
            return SourceState.LIBRARY_MISSING
        if self.catalog_db.exists():
            return SourceState.READY
        return SourceState.INDEX_MISSING

    def load(self):
        """Block the first load, then delegate to the fixture catalog."""
        self.load_calls += 1
        self.started.set()
        if self.load_calls == 1 and not self.release.wait(timeout=5):
            raise TimeoutError
        return CatalogSource(config=self.config).load()


def capture_notifications(app, monkeypatch):
    notifications = []
    original_notify = app.notify

    def notify(message, **kwargs) -> None:
        notifications.append((message, kwargs))
        original_notify(message, **kwargs)

    monkeypatch.setattr(app, "notify", notify)
    return notifications


async def wait_until(predicate, pilot, message):
    deadline = asyncio.get_running_loop().time() + 2
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await pilot.pause(0.01)
    raise AssertionError(message)


async def test_catalog_loads_and_selects_first_part(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        parts_list = app.query_one("#parts-list", PartsList)
        assert parts_list.row_count == 5
        view = app.query_one("#catalog-view", CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "3001"


async def test_catalog_load_failure_clears_loading(fixture_config):
    class FailingSource(CatalogSource):
        """Catalog source that simulates an unexpected load failure."""

        def load(self) -> Never:
            """Raise an unexpected error from the worker boundary."""
            raise RuntimeError("boom")

    app = app_module.PyldrawTuiApp(source=FailingSource(config=fixture_config))
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        view = app.query_one("#catalog-view", CatalogView)
        assert not view.loading


async def test_catalog_load_in_progress_notifies(fixture_config, tmp_path, monkeypatch):
    release = threading.Event()
    marker_db = tmp_path / "marker-catalog.db"
    marker_db.write_text("existing index")
    source = BlockingCatalogSource(
        config=fixture_config,
        catalog_db=marker_db,
        release=release,
    )
    app = app_module.PyldrawTuiApp(source=source)
    notifications = capture_notifications(app, monkeypatch)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(source.started.is_set, pilot, "catalog load did not start")
        assert app._catalog_load_in_progress  # noqa: SLF001

        app._start_catalog_load(SourceState.READY)  # noqa: SLF001

        assert source.load_calls == 1
        assert any(
            message == "Catalog load already in progress."
            for message, _kwargs in notifications
        )
        release.set()
        await wait_for_catalog(app, pilot)


async def test_regenerate_index_waits_for_active_catalog_load(
    fixture_config,
    tmp_path,
    monkeypatch,
):
    release = threading.Event()
    marker_db = tmp_path / "marker-catalog.db"
    marker_db.write_text("existing index")
    source = BlockingCatalogSource(
        config=fixture_config,
        catalog_db=marker_db,
        release=release,
    )
    app = app_module.PyldrawTuiApp(source=source)
    notifications = capture_notifications(app, monkeypatch)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_until(source.started.is_set, pilot, "catalog load did not start")

        regenerate = asyncio.create_task(app.action_regenerate_index())
        await wait_until(
            lambda: any(
                message == "Waiting for the current catalog load to finish…"
                for message, _kwargs in notifications
            ),
            pilot,
            "regenerate did not wait for the active catalog load",
        )

        assert marker_db.exists()
        assert not regenerate.done()

        release.set()
        await regenerate
        await wait_for_catalog(app, pilot)

        assert not marker_db.exists()
        assert source.load_calls == 2


async def test_regenerate_index_notifies_when_catalog_load_cancelled(
    make_app,
    monkeypatch,
):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        marker_db = app.source.catalog_db
        marker_db.parent.mkdir(parents=True, exist_ok=True)
        marker_db.touch()
        notifications = capture_notifications(app, monkeypatch)

        async def cancelled_wait() -> bool:
            return False

        monkeypatch.setattr(app, "_wait_for_catalog_load", cancelled_wait)

        await app.action_regenerate_index()

        assert marker_db.exists()
        assert any(
            message == "Catalog load was cancelled; regenerate index did not run."
            and kwargs.get("severity") == "warning"
            for message, kwargs in notifications
        )


def test_part_metadata_uses_library_relative_path(parts):
    entry = parts.catalog.by_code["3001"]
    text = _metadata_text(entry, parts.path.parent).plain
    assert "parts/3001.dat" in text
    assert str(parts.path.parent) not in text


def test_category_scope_rejects_conflicting_filters():
    with pytest.raises(ValueError, match="exclusive"):
        CategoryScope(category=PartCategory.BRICK, minifig_only=True)
    with pytest.raises(ValueError, match="exclusive"):
        CategoryScope(
            category=PartCategory.BRICK,
            minifig_section=MinifigSection.HATS,
        )


async def test_filter_narrows_list(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("slash")
        assert isinstance(app.focused, FilterBox)
        await pilot.press(*"plate")
        await pilot.pause(0.3)
        parts_list = app.query_one("#parts-list", PartsList)
        assert parts_list.row_count == 2
        view = app.query_one("#catalog-view", CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "3022"


async def test_filter_matches_keywords(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("slash")
        await pilot.press(*"axle")
        await pilot.pause(0.3)
        view = app.query_one("#catalog-view", CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "6157"


async def test_category_selection_scopes_list(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        tree = app.query_one("#category-tree")
        tree.focus()
        # Root is "All parts"; first child is Brick (1).
        await pilot.press("j", "enter")
        await pilot.pause()
        parts_list = app.query_one("#parts-list", PartsList)
        assert parts_list.row_count == 1
        view = app.query_one("#catalog-view", CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "3001"


async def test_row_selection_updates_detail(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("j")  # move from 3001 to 3022
        await pilot.pause()
        subparts = app.query_one("#subpart-tree", SubPartTree)
        assert str(subparts.root.label).startswith("3022")
        labels = [str(child.label) for child in subparts.root.children]
        assert any("STUD" in label for label in labels)
        assert any("[primitive]" in label for label in labels)


async def test_subpart_tree_drills_into_parts(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.focus_part_in_catalog("6157")
        await pilot.pause()
        subparts = app.query_one("#subpart-tree", SubPartTree)
        child_3022 = next(
            child
            for child in subparts.root.children
            if child.data is not None and child.data.code == "3022"
        )
        assert not child_3022.data.primitive
        child_3022.expand()
        await pilot.pause()
        codes = [
            grandchild.data.code
            for grandchild in child_3022.children
            if grandchild.data is not None
        ]
        assert codes == ["STUD", "STUD", "BOX5"]


async def test_sorting_toggles_direction(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        parts_list = app.query_one("#parts-list", PartsList)
        parts_list.sort_by(0)
        await pilot.pause()
        first = parts_list.get_row_at(0)
        assert first[0] == "3001"
        parts_list.sort_by(0)
        await pilot.pause()
        first = parts_list.get_row_at(0)
        assert first[0] == "973"


async def test_sorting_preserves_highlighted_part(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.focus_part_in_catalog("3022")
        await pilot.pause()
        parts_list = app.query_one("#parts-list", PartsList)
        parts_list.sort_by(0)
        await pilot.pause()
        parts_list.sort_by(0)
        await pilot.pause()
        view = app.query_one("#catalog-view", CatalogView)
        assert parts_list.highlighted_entry is not None
        assert parts_list.highlighted_entry.code == "3022"
        assert view.selected_entry is not None
        assert view.selected_entry.code == "3022"


async def test_sorting_restores_highlight_with_single_message(make_app, monkeypatch):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.focus_part_in_catalog("3022")
        await pilot.pause()
        parts_list = app.query_one("#parts-list", PartsList)
        parts_list.sort_by(0)
        await pilot.pause()

        posted = []
        original_post_message = parts_list.post_message

        def post_message(message) -> bool:
            if isinstance(message, PartHighlighted):
                posted.append(message.entry.code if message.entry is not None else None)
            return original_post_message(message)

        monkeypatch.setattr(parts_list, "post_message", post_message)

        parts_list.sort_by(0)
        await pilot.pause()

        assert posted == ["3022"]


async def test_yank_copies_code(make_app, monkeypatch):
    copied: list[str] = []
    monkeypatch.setattr(
        app_module,
        "copy_text",
        lambda text: copied.append(text) or True,
    )
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("y")
        await pilot.pause()
        assert copied == ["3001"]


async def test_export_snippet_chooser_copies_import(make_app, monkeypatch):
    copied: list[str] = []
    monkeypatch.setattr(
        app_module,
        "copy_text",
        lambda text: copied.append(text) or True,
    )
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, ChooserScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert copied == ["from ldraw.library.parts.bricks import Brick2X4"]


async def test_open_web_uses_part_url(make_app, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(
        app_module.webbrowser,
        "open",
        lambda url: opened.append(url) or True,
    )
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("o")
        await pilot.pause()
        assert opened == [
            "https://library.ldraw.org/parts/list?tableSearch=3001.dat",
        ]


async def test_help_modal_opens_and_closes(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


async def test_focus_part_in_catalog_jumps_to_code(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.focus_part_in_catalog("973")
        await pilot.pause()
        view = app.query_one("#catalog-view", CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "973"
        assert view.selected_entry.minifig_section is not None
