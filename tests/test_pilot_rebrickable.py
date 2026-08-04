"""Pilot coverage for offline, live, collection, and LDraw Rebrickable flows."""

from __future__ import annotations

import asyncio

from rebrickable import CatalogStatus, TranslationReport
from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent

import pyldraw3_tui.app as app_module
from pyldraw3_tui.data.rebrickable import CollectionKind, CollectionRow, EntityKind
from pyldraw3_tui.screens.model import ROOT_KEY
from pyldraw3_tui.screens.rebrickable import RebrickableView, UserTokenScreen
from pyldraw3_tui.widgets.rebrickable_translation import RebrickableTranslation
from tests.fakes import FakeRebrickableData
from tests.helpers import wait_for_catalog


async def test_offline_part_browse_needs_no_live_api(make_app, fake_rebrickable):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("3")
        await pilot.pause()

        table = app.query_one("#rb-results", expect_type=DataTable)
        assert table.row_count == 2
        assert table.get_row_at(0)[:2] == ["3001", "Brick 2 x 4"]
        assert not any(call.startswith("live_") for call in fake_rebrickable.calls)
        assert not any(
            call.startswith("collection:") for call in fake_rebrickable.calls
        )
    assert fake_rebrickable.closed


async def test_rebrickable_search_and_locally_constructed_page(
    make_app,
    monkeypatch,
):
    opened: list[str] = []
    monkeypatch.setattr(
        app_module.webbrowser,
        "open",
        lambda url: opened.append(url) or True,
    )
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("3", "slash")
        await pilot.press(*"3022")
        await pilot.pause(0.3)
        await app.workers.wait_for_complete()

        table = app.query_one("#rb-results", expect_type=DataTable)
        assert table.row_count == 1
        assert table.get_row_at(0)[0] == "3022"
        table.focus()
        await pilot.press("o")
        assert opened == ["https://rebrickable.com/parts/3022/"]
        assert not any("cdn.rebrickable.com" in url for url in opened)


async def test_set_inventory_never_renders_image_urls(make_app, fake_rebrickable):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("3")
        app.query_one("#rb-kind", expect_type=Select).value = "set"
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.click("#rb-local-inventory")
        await app.workers.wait_for_complete()

        inventory = app.query_one("#rb-inventory", expect_type=DataTable)
        assert inventory.row_count == 3
        rendered = " ".join(
            str(cell)
            for row in range(inventory.row_count)
            for cell in inventory.get_row_at(row)
        )
        assert "cdn.rebrickable.com" not in rendered
        assert "inventory:10497-1" in fake_rebrickable.calls


async def test_live_details_and_inventory_are_explicit(make_app, fake_rebrickable):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("3")
        app.query_one("#rb-kind", expect_type=Select).value = "set"
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not any(call.startswith("live_") for call in fake_rebrickable.calls)

        await pilot.click("#rb-live-details")
        await app.workers.wait_for_complete()
        assert "live_details:set:10497-1" in fake_rebrickable.calls
        detail = str(app.query_one("#rb-detail", expect_type=Static).render())
        assert "Galaxy Explorer (live)" in detail
        assert "live-set.jpg" not in detail

        await pilot.click("#rb-live-inventory")
        await app.workers.wait_for_complete()
        assert "live_inventory:10497-1" in fake_rebrickable.calls


async def test_collection_uses_masked_session_token(make_app):
    fake = FakeRebrickableData(user_token=False)
    app = make_app(rebrickable_data=fake)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("3")
        view = app.query_one("#rebrickable-view", expect_type=RebrickableView)
        view._total = 201  # noqa: SLF001 - exercise stale async UI state
        view._has_next = True  # noqa: SLF001 - exercise stale async UI state
        app.query_one("#rb-mode", expect_type=Select).value = "collection"
        await pilot.pause()
        await app.workers.wait_for_complete()
        status = str(app.query_one("#rb-state", expect_type=Static).render())
        assert "REBRICKABLE_USER_TOKEN" in status
        page = str(app.query_one("#rb-page-label", expect_type=Static).render())
        assert "0 rows" in page
        assert app.query_one("#rb-next", expect_type=Button).disabled

        await pilot.click("#rb-token")
        assert isinstance(app.screen, UserTokenScreen)
        token = app.screen.query_one("#user-token", expect_type=Input)
        assert token.password
        await pilot.press(*"session-token", "enter")
        await app.workers.wait_for_complete()

        assert fake.user_token_available
        assert "set_user_token" in fake.calls
        assert app.query_one("#rb-results", expect_type=DataTable).row_count == 1


async def test_stale_non_list_selection_is_ignored(
    make_app,
    fake_rebrickable,
) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        view = app.query_one("#rebrickable-view", expect_type=RebrickableView)
        stale_row = CollectionRow(
            key="10497-1",
            title="Galaxy Explorer",
            subtitle="quantity 1",
            entity_kind=EntityKind.SET,
            entity_id="10497-1",
        )
        view._rows = {stale_row.key: stale_row}  # noqa: SLF001
        view._selected_key = stale_row.key  # noqa: SLF001
        view._collection_kind = CollectionKind.PART_LISTS  # noqa: SLF001

        button = app.query_one("#rb-list-contents", expect_type=Button)
        view._list_contents_pressed(Button.Pressed(button))  # noqa: SLF001

        assert view._contents_list_id is None  # noqa: SLF001
        assert not any(call.startswith("list:") for call in fake_rebrickable.calls)


async def test_missing_catalog_can_be_explicitly_refreshed(make_app):
    fake = FakeRebrickableData(status=CatalogStatus.MISSING)
    app = make_app(rebrickable_data=fake)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("3")
        assert app.query_one("#rb-results", expect_type=DataTable).row_count == 0

        await pilot.click("#rb-refresh")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert "refresh" in fake.calls
        assert fake.status is CatalogStatus.READY
        assert app.query_one("#rb-results", expect_type=DataTable).row_count == 2


async def test_displayed_bom_translation_and_exports(
    make_app,
    spaceship_mpd,
    monkeypatch,
):
    copied: list[str] = []
    monkeypatch.setattr(
        app_module,
        "copy_text",
        lambda text: copied.append(text) or True,
    )
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.query_one("#main-tabs", expect_type=TabbedContent).active = "model"
        app.query_one(
            "#model-tabs", expect_type=TabbedContent
        ).active = "tab-rebrickable"
        await app.workers.wait_for_complete()

        translation = app.query_one(
            "#rebrickable-translation", expect_type=RebrickableTranslation
        )
        assert translation.report is not None
        assert translation.report.resolved_count == 2
        assert translation.report.ambiguous_count == 1
        table = app.query_one("#rb-translation-table", expect_type=DataTable)
        assert table.row_count == 3
        assert "ambiguous" in [str(table.get_row_at(row)[0]) for row in range(3)]

        app.action_copy_translation_csv()
        app.action_copy_incomplete_translation_json()
        assert copied[0].startswith("ldraw_part_num,ldraw_color_code")
        assert '"schema":"rebrickable.ldraw.translation.incomplete"' in copied[1]
        assert '"status":"ambiguous"' in copied[1]


async def test_translation_follows_selected_submodel(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        translation = app.query_one(
            "#rebrickable-translation", expect_type=RebrickableTranslation
        )
        assert translation.report is not None
        assert len(translation.report.rows) == 3

        app.query_one("#submodel-select", expect_type=Select).value = "wing.ldr"
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert translation.report is not None
        assert len(translation.report.rows) == 2


async def test_translation_detail_tracks_each_new_report(make_app, spaceship_mpd):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        translation = app.query_one(
            "#rebrickable-translation", expect_type=RebrickableTranslation
        )
        detail = app.query_one("#rb-translation-detail", expect_type=Static)
        assert translation.report is not None
        first = translation.report.rows[0]
        assert f"LDraw {first.ldraw_part_num}" in str(detail.render())

        # Replacing the report leaves the cursor on row 0, so the pane must
        # follow the new first row without a cursor movement to prompt it.
        app.query_one("#submodel-select", expect_type=Select).value = "wing.ldr"
        await pilot.pause()
        await app.workers.wait_for_complete()
        assert translation.report is not None
        replaced = translation.report.rows[0]
        assert replaced.ldraw_part_num != first.ldraw_part_num
        assert translation.selected_row == replaced
        assert f"LDraw {replaced.ldraw_part_num}" in str(detail.render())


async def test_translation_clear_paths_drop_stale_selection(
    make_app,
    spaceship_mpd,
    fake_rebrickable,
    monkeypatch,
) -> None:
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        translation = app.query_one(
            "#rebrickable-translation", expect_type=RebrickableTranslation
        )
        table = app.query_one("#rb-translation-table", expect_type=DataTable)
        table.move_cursor(row=2)
        await pilot.pause()
        assert translation.selected_page_url is not None

        bom_rows = translation._bom_rows  # noqa: SLF001
        parts = translation._parts  # noqa: SLF001
        original_translate = fake_rebrickable.translate

        async def fail_translate(rows, *, parts) -> None:
            del rows, parts
            msg = "fixture translation failure"
            raise RuntimeError(msg)

        monkeypatch.setattr(fake_rebrickable, "translate", fail_translate)
        translation.set_bom(bom_rows, parts)
        await app.workers.wait_for_complete()

        assert translation.report is None
        assert translation.selected_row is None
        assert translation.selected_identifier is None
        assert translation.selected_page_url is None
        assert table.row_count == 0
        assert app.query_one("#rb-enrich-row", expect_type=Button).disabled

        monkeypatch.setattr(fake_rebrickable, "translate", original_translate)
        translation.set_bom(bom_rows, parts)
        await app.workers.wait_for_complete()
        table.move_cursor(row=2)
        await pilot.pause()
        assert translation.selected_row is not None

        translation.set_bom((), parts)
        assert translation.report is None
        assert translation.selected_row is None
        assert translation.selected_identifier is None
        assert translation.selected_page_url is None
        assert table.row_count == 0
        assert app.query_one("#rb-enrich-row", expect_type=Button).disabled


async def test_rapid_submodel_switches_apply_only_latest_translation(
    make_app,
    spaceship_mpd,
    fake_rebrickable,
    monkeypatch,
) -> None:
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        translation = app.query_one(
            "#rebrickable-translation", expect_type=RebrickableTranslation
        )
        assert translation.report is not None
        baseline = fake_rebrickable.calls.count("translate")
        original_translate = fake_rebrickable.translate

        async def slow_translate(rows, *, parts) -> TranslationReport:
            await asyncio.sleep(0.05)
            return await original_translate(rows, parts=parts)

        monkeypatch.setattr(fake_rebrickable, "translate", slow_translate)
        submodel = app.query_one("#submodel-select", expect_type=Select)
        submodel.value = "wing.ldr"
        submodel.value = ROOT_KEY

        for _ in range(100):
            await pilot.pause(0.02)
            if fake_rebrickable.calls.count("translate") > baseline:
                break
        await pilot.pause(0.1)

        assert translation.report is not None
        assert len(translation.report.rows) == 3


async def test_selected_translation_row_verifies_only_its_candidates(
    make_app,
    spaceship_mpd,
    fake_rebrickable,
):
    app = make_app(model_path=spaceship_mpd)
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.query_one(
            "#model-tabs", expect_type=TabbedContent
        ).active = "tab-rebrickable"
        await pilot.pause()
        table = app.query_one("#rb-translation-table", expect_type=DataTable)
        table.move_cursor(row=2)
        await pilot.pause()
        detail = str(
            app.query_one("#rb-translation-detail", expect_type=Static).render()
        )
        assert "multiple color candidates" in detail
        assert "1055" in detail

        app.query_one("#rb-enrich-row", expect_type=Button).press()
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        assert "enrich:2" in fake_rebrickable.calls


def test_rebrickable_view_exposes_only_read_actions():
    action_names = {name for name in dir(RebrickableView) if name.startswith("action_")}
    assert not action_names & {"action_add", "action_update", "action_delete"}
