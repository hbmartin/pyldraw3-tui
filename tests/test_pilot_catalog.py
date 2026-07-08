"""Pilot interaction tests for the catalog screen."""

from __future__ import annotations

import pyldraw3_tui.app as app_module
from pyldraw3_tui.screens.catalog import CatalogView
from pyldraw3_tui.screens.chooser import ChooserScreen
from pyldraw3_tui.screens.help import HelpScreen
from pyldraw3_tui.widgets.filter_box import FilterBox
from pyldraw3_tui.widgets.part_detail import _metadata_text
from pyldraw3_tui.widgets.parts_list import PartsList
from pyldraw3_tui.widgets.subpart_tree import SubPartTree
from tests.helpers import wait_for_catalog


async def test_catalog_loads_and_selects_first_part(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        parts_list = app.query_one("#parts-list", PartsList)
        assert parts_list.row_count == 5
        view = app.query_one("#catalog-view", CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "3001"


def test_part_metadata_uses_library_relative_path(parts):
    entry = parts.catalog.by_code["3001"]
    text = _metadata_text(entry, parts.path.parent).plain
    assert "parts/3001.dat" in text
    assert str(parts.path.parent) not in text


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
