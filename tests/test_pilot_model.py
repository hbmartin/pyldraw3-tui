"""Pilot interaction tests for the model screen."""

from __future__ import annotations

from textual.widgets import Input, Select, Static, TabbedContent

import pyldraw3_tui.app as app_module
from pyldraw3_tui.screens.model import ROOT_KEY, ModelView
from pyldraw3_tui.widgets.bom_table import BomTable
from pyldraw3_tui.widgets.issues_table import IssuesTable
from pyldraw3_tui.widgets.piece_table import PieceTable
from pyldraw3_tui.widgets.stats_panel import StatsPanel
from tests.helpers import wait_for_catalog


async def test_cli_file_opens_model_tab(make_app, car_ldr):
    app = make_app(model_path=car_ldr)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        assert app.query_one("#main-tabs", TabbedContent).active == "model"
        piece_table = app.query_one("#piece-table", PieceTable)
        assert piece_table.row_count == 3
        # Descriptions resolve once the catalog has loaded.
        row = piece_table.get_row_at(0)
        assert row[1] == "3001"
        assert row[2] == "Brick 2 x 4"


async def test_mpd_pieces_expand_submodels(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        piece_table = app.query_one("#piece-table", PieceTable)
        # 1 brick + 2 wings x 2 plates
        assert piece_table.row_count == 5
        # A single-step model shows no step numbers.
        assert piece_table.get_row_at(0)[6] == ""


async def test_building_steps_shown(make_app, car_ldr):
    app = make_app(model_path=car_ldr)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        piece_table = app.query_one("#piece-table", PieceTable)
        steps = [piece_table.get_row_at(row)[6] for row in range(3)]
        assert steps == ["1", "2", "3"]
        stats = app.query_one("#stats-panel", StatsPanel)
        assert "building steps  3" in str(stats.render())


async def test_submodel_selector_switches_model(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        select = app.query_one("#submodel-select", Select)
        select.value = "wing.ldr"
        await pilot.pause()
        piece_table = app.query_one("#piece-table", PieceTable)
        assert piece_table.row_count == 2
        model_view = app.query_one("#model-view", ModelView)
        assert len(model_view.bom_rows) == 2


async def test_invalid_submodel_selection_resets_to_root(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        select = app.query_one("#submodel-select", Select)
        select.value = "wing.ldr"
        await pilot.pause()
        assert select.value == "wing.ldr"

        model_view = app.query_one("#model-view", ModelView)
        model_view._selected_key = "missing.ldr"  # noqa: SLF001
        model_view._render_model()  # noqa: SLF001
        await pilot.pause()

        piece_table = app.query_one("#piece-table", PieceTable)
        assert model_view._selected_key == ROOT_KEY  # noqa: SLF001
        assert select.value == ROOT_KEY
        assert piece_table.row_count == 5
        assert len(model_view.bom_rows) == 3


async def test_bom_rows_and_csv_copy(make_app, spaceship_mpd, monkeypatch):
    copied: list[str] = []
    monkeypatch.setattr(
        app_module,
        "copy_text",
        lambda text: copied.append(text) or True,
    )
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        bom_table = app.query_one("#bom-table", BomTable)
        assert bom_table.row_count == 3
        app.action_copy_bom_csv()
        await pilot.pause()
        assert len(copied) == 1
        assert copied[0].startswith("part,description,colour_code,colour_name")
        assert "3022,Plate 2 x 2,15,White,2" in copied[0]


async def test_summary_stats(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        stats = app.query_one("#stats-panel", StatsPanel)
        rendered = str(stats.render())
        assert "pieces  5" in rendered
        assert "distinct parts  2" in rendered
        assert "building steps  1" in rendered
        assert "bounding box  (true part geometry)" in rendered
        assert "mm)" in rendered


async def test_broken_model_shows_error_card(make_app, broken_ldr):
    app = make_app(model_path=broken_ldr)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        model_view = app.query_one("#model-view", ModelView)
        assert model_view.has_class("errored")
        error = app.query_one("#model-error", Static)
        assert "broken.ldr:2" in str(error.render())


async def test_clean_model_shows_zero_issues(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        assert app.query_one("#issues-table", IssuesTable).row_count == 0
        tabs = app.query_one("#model-tabs", TabbedContent)
        assert str(tabs.get_tab("tab-issues").label) == "Issues (0)"


async def test_issues_tab_lists_validation_problems(make_app, warnings_ldr):
    app = make_app(model_path=warnings_ldr)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        issues_table = app.query_one("#issues-table", IssuesTable)
        assert issues_table.row_count == 4
        rows = [issues_table.get_row_at(row) for row in range(4)]
        assert [row[0] for row in rows] == ["3", "4", "5", "6"]
        assert [str(row[1]) for row in rows] == [
            "warning",
            "warning",
            "error",
            "error",
        ]
        messages = [str(row[2]) for row in rows]
        assert "unknown meta-command !MYEDITOR" in messages[0]
        assert "not orthonormal" in messages[1]
        assert "unknown colour code 99" in messages[2]
        assert "unknown part 9999.dat" in messages[3]
        tabs = app.query_one("#model-tabs", TabbedContent)
        assert str(tabs.get_tab("tab-issues").label) == "Issues (4)"


async def test_unparseable_model_still_lists_issues(make_app, broken_ldr):
    app = make_app(model_path=broken_ldr)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        issues_table = app.query_one("#issues-table", IssuesTable)
        assert issues_table.row_count == 1
        row = issues_table.get_row_at(0)
        assert row[0] == "2"
        assert "Line type subfile" in str(row[2])


async def test_open_model_prompt_loads_model(make_app, car_ldr):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.action_open_model_prompt()
        await pilot.pause()
        await pilot.pause()
        prompt = app.screen.query_one("#model-path-input", Input)
        prompt.value = str(car_ldr)
        prompt.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert app.query_one("#main-tabs", TabbedContent).active == "model"
        assert app.query_one("#piece-table", PieceTable).row_count == 3
