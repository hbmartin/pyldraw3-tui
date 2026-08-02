"""Pilot interaction tests for the model screen."""

from __future__ import annotations

from textual.widgets import Input, Select, Static, TabbedContent

import pyldraw3_tui.app as app_module
from pyldraw3_tui.screens.model import (
    INSTRUCTIONS_MODE,
    MODEL_MODE,
    ROOT_KEY,
    ModelView,
)
from pyldraw3_tui.widgets.bom_table import BomTable
from pyldraw3_tui.widgets.directives_table import DirectivesTable
from pyldraw3_tui.widgets.instruction_details import InstructionDetails
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


async def test_clean_model_shows_zero_issues(make_app, car_ldr):
    app = make_app(model_path=car_ldr)
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
        assert issues_table.row_count == 5
        rows = [issues_table.get_row_at(row) for row in range(5)]
        assert [row[0] for row in rows] == ["warnings.ldr"] * 5
        assert [row[1] for row in rows] == ["3", "4", "5", "6", "—"]
        assert [str(row[2]) for row in rows] == [
            "warning",
            "warning",
            "error",
            "error",
            "warning",
        ]
        messages = [str(row[4]) for row in rows]
        assert "unknown meta-command !MYEDITOR" in messages[0]
        assert "not orthonormal" in messages[1]
        assert "unknown colour code 99" in messages[2]
        assert "unknown part 9999.dat" in messages[3]
        assert "no explicit STEP or ROTSTEP" in messages[4]
        tabs = app.query_one("#model-tabs", TabbedContent)
        assert str(tabs.get_tab("tab-issues").label) == "Issues (5)"


async def test_unparseable_model_still_lists_issues(make_app, broken_ldr):
    app = make_app(model_path=broken_ldr)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        issues_table = app.query_one("#issues-table", IssuesTable)
        assert issues_table.row_count == 1
        row = issues_table.get_row_at(0)
        assert row[0] == "broken.ldr"
        assert row[1] == "2"
        assert row[3] == "parse.invalid_line"
        assert "Line type subfile" in str(row[4])


async def test_instruction_mode_navigation_is_section_local(
    make_app,
    instructions_mpd,
):
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        model_view = app.query_one("#model-view", ModelView)
        mode_select = app.query_one("#view-mode-select", Select)
        section_select = app.query_one("#instruction-section-select", Select)
        step_select = app.query_one("#instruction-step-select", Select)
        tabs = app.query_one("#model-tabs", TabbedContent)
        assert mode_select.value == MODEL_MODE
        assert not tabs.get_tab("tab-pli").display
        assert not tabs.get_tab("tab-directives").display

        await pilot.press("i")
        assert mode_select.value == INSTRUCTIONS_MODE
        assert model_view.has_class("instructions")
        assert tabs.get_tab("tab-pli").display
        assert tabs.get_tab("tab-directives").display
        assert section_select.value == "main.ldr"
        assert step_select.value == 1
        document = model_view._instruction_document  # noqa: SLF001
        assert document is not None
        assert [section.name for section in document.sections] == [
            "main.ldr",
            "sub.ldr",
        ]
        assert [len(section.steps) for section in document.sections] == [4, 3]
        assert [section.name for section in document.orphan_sections] == [
            "orphan.ldr",
        ]

        await pilot.press("]")
        assert step_select.value == 2
        section_select.value = "sub.ldr"
        await pilot.pause()
        assert step_select.value == 1
        step_select.value = 3
        await pilot.pause()

        await pilot.press("i")
        assert mode_select.value == MODEL_MODE
        await pilot.press("i")
        assert mode_select.value == INSTRUCTIONS_MODE
        assert section_select.value == "sub.ldr"
        assert step_select.value == 3


async def test_instruction_step_renders_cumulative_geometry_and_inventories(
    make_app,
    instructions_mpd,
):
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("i")
        step_select = app.query_one("#instruction-step-select", Select)
        step_select.value = 3
        await pilot.pause()

        piece_table = app.query_one("#piece-table", PieceTable)
        assert piece_table.row_count == 6
        assert [piece_table.get_row_at(row)[6] for row in range(6)] == [
            "1",
            "3",
            "3",
            "3",
            "3",
            "3",
        ]
        assert "3901" in [piece_table.get_row_at(row)[1] for row in range(6)]
        pli_table = app.query_one("#pli-table", BomTable)
        assert [pli_table.get_row_at(row)[0] for row in range(3)] == [
            "3001",
            "3022",
            "6157",
        ]
        bom_table = app.query_one("#bom-table", BomTable)
        bom_rows = [
            (bom_table.get_row_at(row)[0], bom_table.get_row_at(row)[3])
            for row in range(2)
        ]
        assert bom_rows == [
            ("3001", 2),
            ("3022", 2),
        ]

        details = str(
            app.query_one("#instruction-details", InstructionDetails).render(),
        )
        assert "instruction step  3 of 4" in details
        assert "added occurrences  5" in details
        assert "cumulative occurrences  6" in details
        assert "camera  angles=(30.0, 45.0)" in details
        assert "multi-step group  1" in details
        assert "page break before  yes" in details
        assert "suppressed  yes" in details

        directives = app.query_one("#directives-table", DirectivesTable)
        assert directives.row_count == 13
        rows = [directives.get_row_at(row) for row in range(13)]
        assert {row[1] for row in rows} >= {"highlight", "arrow"}
        arrow = next(row for row in rows if row[1] == "arrow")
        assert '"label": "Attach"' in arrow[2].plain
        legacy_bom = next(
            row
            for row in rows
            if row[1] == "inventory_ignore_begin" and "BOM" in row[3].plain
        )
        assert legacy_bom[3].plain == "0 LPUB BOM BEGIN IGN"
        unsupported = next(row for row in rows if row[1] == "unsupported_lpub")
        assert unsupported[3].plain == "0 !LPUB SOMETHING KEEP RAW"

        step_select.value = 2
        await pilot.pause()
        details = str(
            app.query_one("#instruction-details", InstructionDetails).render(),
        )
        assert "rotation  REL (0, 45, 0)" in details
        assert app.query_one("#piece-table", PieceTable).row_count == 1

        step_select.value = 4
        await pilot.pause()
        details = str(
            app.query_one("#instruction-details", InstructionDetails).render(),
        )
        assert "rotation  END" in details
        assert "callouts  ROTATED: sub.ldr" in details
        assert app.query_one("#piece-table", PieceTable).row_count == 9
        pli_table = app.query_one("#pli-table", BomTable)
        assert [pli_table.get_row_at(row)[0] for row in range(3)] == [
            "3001",
            "3022",
            "embedded",
        ]


async def test_instruction_bom_copy_uses_selected_step(
    make_app,
    instructions_mpd,
    monkeypatch,
):
    copied: list[str] = []
    monkeypatch.setattr(
        app_module,
        "copy_text",
        lambda text: copied.append(text) or True,
    )
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("i")
        app.query_one("#instruction-step-select", Select).value = 3
        await pilot.pause()
        app.action_copy_bom_csv()
        await pilot.pause()
        assert "3001,Brick 2 x 4,4,Red,2" in copied[-1]
        assert "6157" not in copied[-1]

        await pilot.press("i")
        app.action_copy_bom_csv()
        await pilot.pause()
        assert "6157" in copied[-1]


async def test_instruction_issues_include_orphan_section(
    make_app,
    instructions_mpd,
):
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        issues_table = app.query_one("#issues-table", IssuesTable)
        assert issues_table.row_count == 1
        row = issues_table.get_row_at(0)
        assert row[0] == "orphan.ldr"
        assert row[1] == "—"
        assert row[2].plain == "warning"
        assert row[3] == "orphan-section"


async def test_instruction_step_keys_clamp_at_section_bounds(
    make_app,
    instructions_mpd,
):
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("i")
        step_select = app.query_one("#instruction-step-select", Select)
        assert step_select.value == 1
        await pilot.press("[")
        assert step_select.value == 1
        for _ in range(5):
            await pilot.press("]")
        assert step_select.value == 4
        await pilot.press("]")
        assert step_select.value == 4


async def test_instruction_selection_fallback_synchronizes_step(
    make_app,
    instructions_mpd,
):
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        model_view = app.query_one("#model-view", ModelView)
        model_view._selected_instruction_step = 999  # noqa: SLF001

        selection = model_view._instruction_selection()  # noqa: SLF001

        assert selection is not None
        section, step = selection
        assert step is section.steps[0]
        assert model_view._selected_instruction_step == step.number  # noqa: SLF001


async def test_error_load_exits_instructions_mode(
    make_app,
    instructions_mpd,
    broken_ldr,
):
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("i")
        model_view = app.query_one("#model-view", ModelView)
        assert model_view.has_class("instructions")

        model_view.load_model(broken_ldr)
        await pilot.pause()
        assert model_view.has_class("errored")
        assert not model_view.has_class("instructions")
        assert app.query_one("#view-mode-select", Select).value == MODEL_MODE
        submodel_select = app.query_one("#submodel-select", Select)
        assert submodel_select.value is Select.NULL
        assert submodel_select._options == [("", Select.NULL)]  # noqa: SLF001
        tabs = app.query_one("#model-tabs", TabbedContent)
        assert not tabs.get_tab("tab-pli").display
        assert not tabs.get_tab("tab-directives").display


async def test_opening_another_file_resets_and_clears_instruction_state(
    make_app,
    instructions_mpd,
    car_ldr,
    broken_ldr,
):
    app = make_app(model_path=instructions_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("i")
        app.query_one("#instruction-section-select", Select).value = "sub.ldr"
        await pilot.pause()
        app.query_one("#instruction-step-select", Select).value = 3
        await pilot.pause()

        model_view = app.query_one("#model-view", ModelView)
        model_view.load_model(car_ldr)
        await pilot.pause()
        assert app.query_one("#view-mode-select", Select).value == MODEL_MODE
        assert app.query_one("#instruction-section-select", Select).value == "car.ldr"
        assert app.query_one("#instruction-step-select", Select).value == 1

        model_view.load_model(broken_ldr)
        await pilot.pause()
        assert model_view._instruction_document is None  # noqa: SLF001
        assert app.query_one("#piece-table", PieceTable).row_count == 0


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
