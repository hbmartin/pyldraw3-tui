"""Pilot interaction tests for the catalog screen."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Never

import pytest
from ldraw import Diagnostic, DiagnosticCode, Severity
from ldraw.parts import MinifigSection, PartCategory
from ldraw.session import LDrawSession
from textual.widgets import Static

import pyldraw3_tui.app as app_module
from pyldraw3_tui.data.source import CatalogSource, SourceState
from pyldraw3_tui.messages import CategoryScope, PartHighlighted
from pyldraw3_tui.screens.catalog import CatalogView
from pyldraw3_tui.screens.chooser import ChooserScreen
from pyldraw3_tui.screens.help import HelpScreen
from pyldraw3_tui.widgets.colour_swatches import ColourSwatches
from pyldraw3_tui.widgets.connections import (
    ConnectionDiagnosticsTable,
    ConnectionFeatureTable,
    PartConnections,
)
from pyldraw3_tui.widgets.filter_box import FilterBox
from pyldraw3_tui.widgets.issues_table import IssuesTable
from pyldraw3_tui.widgets.part_detail import _metadata_text
from pyldraw3_tui.widgets.parts_list import PartsList
from pyldraw3_tui.widgets.subpart_tree import SubPartTree
from tests.helpers import wait_for_catalog

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from ldraw import PartGeometry
    from ldraw.session import CatalogPreparationResult

    from pyldraw3_tui.app import PyldrawTuiApp


@dataclass(slots=True)
class BlockingCatalogSource(CatalogSource):
    """Catalog source that blocks the first load until a test releases it."""

    marker_db: Path
    release: threading.Event
    started: threading.Event = field(init=False)
    load_calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.started = threading.Event()

    @property
    def catalog_db(self) -> Path:
        """Return the marker index path controlled by the test."""
        return self.marker_db

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
        return CatalogSource.load(self)


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


def test_blocking_catalog_source_preserves_connection_sources(
    fixture_config,
    tmp_path: Path,
) -> None:
    studio = tmp_path / "studio.json"
    studio.write_text(
        '{"parts": [{"part_id": "3901", "connections": '
        '[{"id": "test-bar", "type": "bar", "position": [0, 0, 0], '
        '"axis": [0, 1, 0], "gender": "male"}]}]}'
    )
    release = threading.Event()
    release.set()
    source = BlockingCatalogSource(
        config=fixture_config,
        marker_db=tmp_path / "catalog.db",
        release=release,
        studio_metadata=(studio,),
    )

    parts = source.load()

    assert [
        feature.feature_id for feature in parts.connection_metadata("3901").features
    ] == ["test-bar"]


async def test_catalog_loads_and_selects_first_part(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        parts_list = app.query_one("#parts-list", expect_type=PartsList)
        assert parts_list.row_count == 5
        view = app.query_one("#catalog-view", expect_type=CatalogView)
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
        view = app.query_one("#catalog-view", expect_type=CatalogView)
        assert not view.loading


async def test_catalog_preparation_diagnostics_are_notified(
    make_app: Callable[..., PyldrawTuiApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_prepare = LDrawSession.prepare_catalog
    warning = Diagnostic(
        message="catalog index could not be persisted",
        severity=Severity.WARNING,
        code=DiagnosticCode.CATALOG_PERSIST_FAILED,
    )

    def prepare_with_warning(
        session: LDrawSession,
        **kwargs,
    ) -> CatalogPreparationResult:
        result = original_prepare(session, **kwargs)
        return replace(result, diagnostics=(*result.diagnostics, warning))

    monkeypatch.setattr(LDrawSession, "prepare_catalog", prepare_with_warning)
    app = make_app()
    notifications = capture_notifications(app, monkeypatch)

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)

        assert any(
            message == warning.message and kwargs.get("severity") == "warning"
            for message, kwargs in notifications
        )


async def test_catalog_load_in_progress_notifies(fixture_config, tmp_path, monkeypatch):
    release = threading.Event()
    marker_db = tmp_path / "marker-catalog.db"
    marker_db.write_text("existing index")
    source = BlockingCatalogSource(
        config=fixture_config,
        marker_db=marker_db,
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
        marker_db=marker_db,
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


def test_part_metadata_includes_geometry(parts):
    entry = parts.catalog.by_code["3001"]
    text = _metadata_text(entry, parts.path.parent, parts.geometry(entry.code)).plain
    assert "80 x 28 x 40 LDU (32.0 x 11.2 x 16.0 mm)" in text
    assert "4 top" in text
    assert "connections  4" in text
    assert "coverage  partial" in text


async def test_part_connections_show_primitive_features(
    make_app: Callable[..., PyldrawTuiApp],
) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)

        metadata = app.query_one("#part-metadata", expect_type=Static)
        assert "connections  4" in str(metadata.render())
        assert "coverage  partial" in str(metadata.render())

        summary = app.query_one("#connection-summary", expect_type=Static)
        assert "coverage  partial" in str(summary.render())
        table = app.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        )
        assert table.row_count == 4
        row = table.get_row_at(0)
        assert row[0] == "stud"
        assert row[1] == "male"
        assert row[2] == "primitive"
        assert row[3] == "100.0%"
        detail = app.query_one("#connection-feature-detail", expect_type=Static)
        assert "position  (-30, -24, -10)" in str(detail.render())
        assert "occupancy  free" in str(detail.render())


async def test_part_connections_show_none_coverage(
    make_app: Callable[..., PyldrawTuiApp],
) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.focus_part_in_catalog("3901")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        summary = app.query_one("#connection-summary", expect_type=Static)
        assert "coverage  none" in str(summary.render())
        table = app.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        )
        assert table.row_count == 0


async def test_part_connection_table_shows_occupancy_and_compatibility(
    make_app: Callable[..., PyldrawTuiApp],
) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        assert app.parts is not None
        feature = replace(
            app.parts.connections("3001")[0],
            feature_id="shortcut [/] feature",
            occupied=True,
            occupied_by="shortcut [/] assembly",
            compatible_parts=("3002", "[bold]3003[/bold]"),
        )
        geometry = replace(app.parts.geometry("3001"), connections=(feature,))
        app.query_one("#part-connections", expect_type=PartConnections).show_geometry(
            geometry
        )
        await pilot.pause()

        detail = app.query_one("#connection-feature-detail", expect_type=Static)
        rendered = str(detail.render())
        assert "feature ID  shortcut [/] feature" in rendered
        assert "occupancy  occupied by shortcut [/] assembly" in rendered
        assert "compatible  3002, [bold]3003[/bold]" in rendered


async def test_part_connection_diagnostics_stay_out_of_model_issues(
    make_app: Callable[..., PyldrawTuiApp],
    tmp_path: Path,
) -> None:
    studio = tmp_path / "studio.json"
    studio.write_text(
        """{
          "parts": [{
            "part_id": "3001",
            "connections": [{
              "id": "studio-stud",
              "type": "stud",
              "position": [0, 0, 0],
              "axis": [0, 1, 0],
              "gender": "male",
              "radius": 6,
              "length": 4,
              "future_field": true
            }]
          }]
        }"""
    )
    app = make_app(studio_metadata=(studio,))
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)

        diagnostics = app.query_one(
            "#connection-diagnostics", expect_type=ConnectionDiagnosticsTable
        )
        assert diagnostics.row_count == 1
        assert diagnostics.get_row_at(0)[1] == "connection.unsupported_option"
        assert app.query_one("#issues-table", expect_type=IssuesTable).row_count == 0


async def test_invalid_studio_document_is_shown_as_connection_diagnostic(
    make_app: Callable[..., PyldrawTuiApp],
    tmp_path: Path,
) -> None:
    studio = tmp_path / "studio.json"
    studio.write_text("not json")
    app = make_app(studio_metadata=(studio,))

    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)

        diagnostics = app.query_one(
            "#connection-diagnostics", expect_type=ConnectionDiagnosticsTable
        )
        assert diagnostics.row_count == 1
        assert "could not read Studio connectivity JSON" in str(
            diagnostics.get_row_at(0)[3]
        )


async def test_part_connections_show_geometry_diagnostics(
    make_app: Callable[..., PyldrawTuiApp],
) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        assert app.parts is not None
        geometry = replace(
            app.parts.geometry("3001"),
            connection_metadata=None,
            diagnostics=(
                Diagnostic(
                    message="unresolved fixture subpart",
                    code=DiagnosticCode.PART_REFERENCE_UNRESOLVED,
                ),
            ),
        )

        app.query_one("#part-connections", expect_type=PartConnections).show_geometry(
            geometry
        )

        diagnostics = app.query_one(
            "#connection-diagnostics", expect_type=ConnectionDiagnosticsTable
        )
        summary = app.query_one("#connection-summary", expect_type=Static)
        features = app.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        )
        assert "coverage  unavailable" in str(summary.render())
        assert features.row_count == 4
        assert diagnostics.row_count == 1
        row = diagnostics.get_row_at(0)
        assert row[1] == "part.reference_unresolved"
        assert str(row[3]) == "unresolved fixture subpart"


async def test_part_geometry_failure_is_nonfatal(
    make_app: Callable[..., PyldrawTuiApp],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        assert app.parts is not None

        def fail_geometry(_code: str) -> Never:
            message = "fixture [/] became unreadable"
            raise RuntimeError(message)

        monkeypatch.setattr(app.parts, "geometry", fail_geometry)
        app.focus_part_in_catalog("3022")
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        metadata = app.query_one("#part-metadata", expect_type=Static)
        summary = app.query_one("#connection-summary", expect_type=Static)
        assert "geometry  unavailable: fixture [/] became unreadable" in str(
            metadata.render()
        )
        assert "Connections unavailable: fixture [/] became unreadable" in str(
            summary.render()
        )
        assert "Unexpected geometry failure for 3022" in caplog.text


async def test_part_geometry_requests_are_serialized_and_coalesced(
    make_app: Callable[..., PyldrawTuiApp],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        assert app.parts is not None
        original_geometry = app.parts.geometry
        started = threading.Event()
        release = threading.Event()
        calls: list[str] = []
        active = 0
        max_active = 0
        lock = threading.Lock()

        def blocking_geometry(code: str) -> PartGeometry:
            nonlocal active, max_active
            with lock:
                calls.append(code)
                active += 1
                max_active = max(max_active, active)
            try:
                if code == "3022":
                    started.set()
                    if not release.wait(timeout=5):
                        raise TimeoutError
                return original_geometry(code)
            finally:
                with lock:
                    active -= 1

        monkeypatch.setattr(app.parts, "geometry", blocking_geometry)
        app.focus_part_in_catalog("3022")
        await wait_until(started.is_set, pilot, "part geometry did not start")
        app.focus_part_in_catalog("3901")
        await pilot.pause()
        app.focus_part_in_catalog("6157")
        await pilot.pause()

        assert calls == ["3022"]

        release.set()
        await wait_for_catalog(app, pilot)

        metadata = app.query_one("#part-metadata", expect_type=Static)
        assert "code  6157" in str(metadata.render())
        assert calls == ["3022", "6157"]
        assert max_active == 1


async def test_palette_marks_solid_colours(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        swatches = app.query_one("#palette-swatches", expect_type=ColourSwatches)
        lines = str(swatches.render()).splitlines()
        solid = [line for line in lines if "[solid]" in line]
        assert len(solid) == 5
        assert not any("Chrome" in line or "Trans" in line for line in solid)


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
        parts_list = app.query_one("#parts-list", expect_type=PartsList)
        assert parts_list.row_count == 2
        view = app.query_one("#catalog-view", expect_type=CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "3022"


async def test_filter_matches_keywords(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("slash")
        await pilot.press(*"axle")
        await pilot.pause(0.3)
        view = app.query_one("#catalog-view", expect_type=CatalogView)
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
        parts_list = app.query_one("#parts-list", expect_type=PartsList)
        assert parts_list.row_count == 1
        view = app.query_one("#catalog-view", expect_type=CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "3001"


async def test_row_selection_updates_detail(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        await pilot.press("j")  # move from 3001 to 3022
        await pilot.pause()
        subparts = app.query_one("#subpart-tree", expect_type=SubPartTree)
        assert str(subparts.root.label).startswith("3022")
        labels = [str(child.label) for child in subparts.root.children]
        assert any("stud" in label for label in labels)
        assert any("[primitive]" in label for label in labels)


async def test_subpart_tree_drills_into_parts(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        app.focus_part_in_catalog("6157")
        await pilot.pause()
        subparts = app.query_one("#subpart-tree", expect_type=SubPartTree)
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
        assert codes == ["stud", "stud", "box5"]


async def test_sorting_toggles_direction(make_app):
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await wait_for_catalog(app, pilot)
        parts_list = app.query_one("#parts-list", expect_type=PartsList)
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
        parts_list = app.query_one("#parts-list", expect_type=PartsList)
        parts_list.sort_by(0)
        await pilot.pause()
        parts_list.sort_by(0)
        await pilot.pause()
        view = app.query_one("#catalog-view", expect_type=CatalogView)
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
        parts_list = app.query_one("#parts-list", expect_type=PartsList)
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
        view = app.query_one("#catalog-view", expect_type=CatalogView)
        assert view.selected_entry is not None
        assert view.selected_entry.code == "973"
        assert view.selected_entry.minifig_section is not None
