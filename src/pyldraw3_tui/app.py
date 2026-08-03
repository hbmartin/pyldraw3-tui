"""The pyldraw3-tui application shell: tabs, bindings, and actions."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING, ClassVar

from ldraw.bom import rows_to_csv, rows_to_json
from rebrickable import ConfigLoadError as RebrickableConfigLoadError
from rebrickable.exports import to_json, translation_to_csv
from textual import work
from textual.app import App
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane
from textual.worker import WorkerCancelled, WorkerFailed

from pyldraw3_tui.clipboard import copy_text
from pyldraw3_tui.commands import PyldrawTuiCommands
from pyldraw3_tui.data.rebrickable import (
    RebrickableData,
    RebrickableDataProtocol,
)
from pyldraw3_tui.data.search import SearchIndex
from pyldraw3_tui.data.snippets import code_snippet, import_snippet, piece_snippet
from pyldraw3_tui.data.source import CatalogSource, SourceState
from pyldraw3_tui.data.web import part_url
from pyldraw3_tui.screens.catalog import CatalogView
from pyldraw3_tui.screens.chooser import ChooserScreen, TextScreen
from pyldraw3_tui.screens.help import HelpScreen, binding_sections
from pyldraw3_tui.screens.model import ModelView
from pyldraw3_tui.screens.open_model import OpenModelScreen
from pyldraw3_tui.screens.rebrickable import RebrickableView
from pyldraw3_tui.screens.setup import SetupScreen
from pyldraw3_tui.theme import DARK_THEME, toggled_theme
from pyldraw3_tui.widgets.category_tree import CategoryTree
from pyldraw3_tui.widgets.parts_list import PartsList
from pyldraw3_tui.widgets.piece_table import PieceTable
from pyldraw3_tui.widgets.rebrickable_translation import RebrickableTranslation
from pyldraw3_tui.widgets.subpart_tree import SubPartTree

if TYPE_CHECKING:
    from pathlib import Path

    from ldraw.parts import CatalogEntry, Parts
    from textual.app import ComposeResult
    from textual.worker import Worker

    from pyldraw3_tui.screens.help import BindingSections


class PyldrawTuiApp(App[None]):
    """Read-only browser for LDraw models and Rebrickable catalog data."""

    TITLE = "pyldraw3-tui"
    COMMANDS: ClassVar = {*App.COMMANDS, PyldrawTuiCommands}
    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("1", "show_tab('catalog')", "Catalog"),
        Binding("2", "show_tab('model')", "Model"),
        Binding("3", "show_tab('rebrickable')", "Rebrickable"),
        Binding("y", "yank_code", "Yank code"),
        Binding("Y", "yank_chooser", "Yank…", show=False),
        Binding("o", "open_web", "Open page"),
        Binding("e", "export_snippet", "Snippet"),
        Binding("colon", "command_palette", "Palette", key_display=":", show=False),
        Binding("ctrl+t", "toggle_theme", "Theme", show=False),
    ]

    def __init__(
        self,
        *,
        source: CatalogSource | None = None,
        model_path: Path | None = None,
        rebrickable_data: RebrickableDataProtocol | None = None,
    ) -> None:
        super().__init__()
        self.source = (
            source if source is not None else (CatalogSource.from_default_config())
        )
        self.parts: Parts | None = None
        self.search_index: SearchIndex | None = None
        self._model_path = model_path
        self._catalog_worker: Worker[None] | None = None
        self._rebrickable_config_error: str | None = None
        if rebrickable_data is not None:
            self.rebrickable_data: RebrickableDataProtocol | None = rebrickable_data
        else:
            try:
                self.rebrickable_data = RebrickableData()
            except RebrickableConfigLoadError as error:
                self.rebrickable_data = None
                self._rebrickable_config_error = str(error)

    def compose(self) -> ComposeResult:
        """Lay out the header, three top-level tabs, and key-hint footer."""
        yield Header()
        initial = "model" if self._model_path is not None else "catalog"
        with TabbedContent(initial=initial, id="main-tabs"):
            with TabPane("Catalog", id="catalog"):
                yield CatalogView(id="catalog-view")
            with TabPane("Model", id="model"):
                yield ModelView(id="model-view")
            with TabPane("Rebrickable", id="rebrickable"):
                yield RebrickableView(
                    self.rebrickable_data,
                    config_error=self._rebrickable_config_error,
                    id="rebrickable-view",
                )
        yield Footer()

    def on_mount(self) -> None:
        """Classify the data source and start loading the catalog."""
        self.theme = DARK_THEME
        model_view = self.query_one("#model-view", expect_type=ModelView)
        model_view.set_source(self.source)
        model_view.set_rebrickable_data(self.rebrickable_data)
        if self._model_path is not None:
            model_view.load_model(self._model_path)
        state = self.source.classify()
        if state is SourceState.LIBRARY_MISSING:
            self.push_screen(SetupScreen(self.source), self._setup_finished)
            return
        self._start_catalog_load(state)

    def _setup_finished(self, _result: None) -> None:
        self._start_catalog_load(self.source.classify())

    def _start_catalog_load(self, state: SourceState) -> None:
        if state is SourceState.LIBRARY_MISSING:
            self.notify("LDraw library still missing.", severity="error")
            return
        if self._catalog_load_in_progress:
            self.notify("Catalog load already in progress.", timeout=5)
            return
        if state is not SourceState.READY:
            self.notify(
                "Building the parts index — the first load can take a while…",
                timeout=10,
            )
        self.query_one("#catalog-view", expect_type=CatalogView).loading = True
        self._catalog_worker = self._load_catalog()

    @property
    def _catalog_load_in_progress(self) -> bool:
        worker = self._catalog_worker
        return worker is not None and not worker.is_finished

    async def _wait_for_catalog_load(self) -> bool:
        if not self._catalog_load_in_progress:
            return True
        worker = self._catalog_worker
        if worker is None:
            return True
        self.notify("Waiting for the current catalog load to finish…", timeout=5)
        try:
            await worker.wait()
        except WorkerCancelled:
            return False
        except WorkerFailed:
            return True
        return True

    @work(thread=True, exclusive=True, group="catalog-load")
    def _load_catalog(self) -> None:
        """Load (and index) the catalog off the UI thread."""
        try:
            parts = self.source.load()
        except Exception as error:  # noqa: BLE001
            reason = str(error) or type(error).__name__
            self.call_from_thread(self._catalog_failed, reason)
            return
        self.call_from_thread(self._catalog_ready, parts)

    def _catalog_failed(self, reason: str) -> None:
        self.query_one("#catalog-view", expect_type=CatalogView).loading = False
        self.notify(f"Could not load the catalog: {reason}", severity="error")

    def _catalog_ready(self, parts: Parts) -> None:
        self.parts = parts
        self.search_index = SearchIndex.from_catalog(parts.catalog)
        catalog_view = self.query_one("#catalog-view", expect_type=CatalogView)
        catalog_view.set_parts(parts, self.search_index)
        catalog_view.loading = False
        self.query_one("#model-view", expect_type=ModelView).set_parts(parts)
        if self.query_one("#main-tabs", expect_type=TabbedContent).active == "catalog":
            self.query_one("#parts-list", expect_type=PartsList).focus()
        self.notify(f"Catalog loaded: {len(parts.catalog.by_code)} parts")

    async def on_unmount(self) -> None:
        """Close Rebrickable resources without persisting credentials."""
        if self.rebrickable_data is not None:
            await self.rebrickable_data.close()

    # ------------------------------------------------------------- helpers

    def _selected_entry(self) -> CatalogEntry | None:
        entry = self.query_one("#catalog-view", expect_type=CatalogView).selected_entry
        if entry is None:
            self.notify("No part selected.", severity="warning")
        return entry

    def _copy(self, text: str, description: str) -> None:
        if copy_text(text):
            self.notify(f"Copied {description}.")
        else:
            self.push_screen(TextScreen(text))

    def _copy_choice(self, choice: str | None) -> None:
        if choice is not None:
            self._copy(choice, "selection")

    def focus_part_in_catalog(self, code: str) -> None:
        """Switch to the catalog tab and select a part by code."""
        self.query_one("#main-tabs", expect_type=TabbedContent).active = "catalog"
        self.query_one("#catalog-view", expect_type=CatalogView).focus_part(code)

    def help_sections(self) -> BindingSections:
        """Collect binding tables for the help screen, grouped by owner."""
        return binding_sections(
            [
                ("Global", PyldrawTuiApp.BINDINGS),
                ("Catalog", CatalogView.BINDINGS),
                ("Model", ModelView.BINDINGS),
                ("Rebrickable", RebrickableView.BINDINGS),
                ("Trees", [*CategoryTree.BINDINGS, *SubPartTree.BINDINGS]),
                ("Tables", PartsList.BINDINGS),
            ],
        )

    # ------------------------------------------------------------- actions

    def action_show_tab(self, tab: str) -> None:
        """Activate the Catalog, Model, or Rebrickable tab."""
        self.query_one("#main-tabs", expect_type=TabbedContent).active = tab
        if tab == "model":
            self.query_one("#piece-table", expect_type=PieceTable).focus()
        elif tab == "rebrickable":
            self.query_one("#rb-results").focus()

    def action_toggle_theme(self) -> None:
        """Switch between the dark and light themes."""
        self.theme = toggled_theme(self.theme)

    def action_help(self) -> None:
        """Show the key-binding reference."""
        self.push_screen(HelpScreen(self.help_sections()))

    def action_yank_code(self) -> None:
        """Copy the selected LDraw or Rebrickable identifier."""
        if self._in_rebrickable_context():
            if (identifier := self._selected_rebrickable_identifier()) is not None:
                self._copy(identifier, f"identifier {identifier}")
            else:
                self.notify("No Rebrickable entity selected.", severity="warning")
            return
        if (entry := self._selected_entry()) is not None:
            self._copy(entry.code, f"code {entry.code}")

    def action_yank_chooser(self) -> None:
        """Choose which part field to copy."""
        if self._in_rebrickable_context():
            identifier = self._selected_rebrickable_identifier()
            if identifier is None:
                self.notify("No Rebrickable entity selected.", severity="warning")
                return
            options = [(f"Identifier — {identifier}", identifier)]
            if (url := self._selected_rebrickable_url()) is not None:
                options.append((f"Page — {url}", url))
            self.push_screen(
                ChooserScreen("Copy what?", options),
                self._copy_choice,
            )
            return
        if (entry := self._selected_entry()) is None:
            return
        options = [(f"Description — {entry.description}", entry.description)]
        if (import_line := import_snippet(entry)) is not None:
            options.append((f"Import — {import_line}", import_line))
        options.append((f"Code — {entry.code}", entry.code))
        self.push_screen(ChooserScreen("Copy what?", options), self._copy_choice)

    def action_export_snippet(self) -> None:
        """Choose a Python snippet form for the selected part."""
        if self._in_rebrickable_context():
            self.notify(
                "Use the command palette to copy Rebrickable translation CSV/JSON.",
                severity="warning",
            )
            return
        if (entry := self._selected_entry()) is None:
            return
        options: list[tuple[str, str]] = []
        if (import_line := import_snippet(entry)) is not None:
            options.append((f"Library import — {import_line}", import_line))
        placement = piece_snippet(entry)
        options.append((f"Piece placement — {placement}", placement))
        bare = code_snippet(entry)
        options.append((f"Bare code — {bare}", bare))
        self.push_screen(
            ChooserScreen("Export Python snippet", options),
            self._copy_choice,
        )

    def action_open_web(self) -> None:
        """Open the selected entity's locally constructed public page."""
        if self._in_rebrickable_context():
            if (url := self._selected_rebrickable_url()) is not None:
                webbrowser.open(url)
                self.notify("Opened selected entity on Rebrickable.")
            else:
                self.notify("No Rebrickable page is available.", severity="warning")
            return
        if (entry := self._selected_entry()) is not None:
            webbrowser.open(part_url(entry.code))
            self.notify(f"Opened {entry.code} on ldraw.org.")

    def _selected_rebrickable_url(self) -> str | None:
        tabs = self.query_one("#main-tabs", expect_type=TabbedContent)
        if tabs.active == "rebrickable":
            return self.query_one(
                "#rebrickable-view", expect_type=RebrickableView
            ).selected_page_url
        if tabs.active == "model":
            model_tabs = self.query_one("#model-tabs", expect_type=TabbedContent)
            if model_tabs.active == "tab-rebrickable":
                return self.query_one(
                    "#rebrickable-translation",
                    expect_type=RebrickableTranslation,
                ).selected_page_url
        return None

    def _in_rebrickable_context(self) -> bool:
        tabs = self.query_one("#main-tabs", expect_type=TabbedContent)
        if tabs.active == "rebrickable":
            return True
        if tabs.active != "model":
            return False
        return (
            self.query_one("#model-tabs", expect_type=TabbedContent).active
            == "tab-rebrickable"
        )

    def _selected_rebrickable_identifier(self) -> str | None:
        tabs = self.query_one("#main-tabs", expect_type=TabbedContent)
        if tabs.active == "rebrickable":
            return self.query_one(
                "#rebrickable-view", expect_type=RebrickableView
            ).selected_identifier
        if tabs.active == "model":
            model_tabs = self.query_one("#model-tabs", expect_type=TabbedContent)
            if model_tabs.active == "tab-rebrickable":
                return self.query_one(
                    "#rebrickable-translation",
                    expect_type=RebrickableTranslation,
                ).selected_identifier
        return None

    def action_open_model_prompt(self) -> None:
        """Prompt for a model path and open it in the Model tab."""
        self.push_screen(OpenModelScreen(), self._open_model)

    def _open_model(self, path: str | None) -> None:
        if not path:
            return
        self.query_one("#main-tabs", expect_type=TabbedContent).active = "model"
        self.query_one("#model-view", expect_type=ModelView).load_model(path)

    async def action_regenerate_index(self) -> None:
        """Delete the persistent index and rebuild it from the library."""
        if not await self._wait_for_catalog_load():
            self.notify(
                "Catalog load was cancelled; regenerate index did not run.",
                severity="warning",
            )
            return
        self.source.catalog_db.unlink(missing_ok=True)
        self._start_catalog_load(self.source.classify())

    def action_copy_bom_csv(self) -> None:
        """Copy the currently displayed bill of materials as CSV."""
        self._copy_bom(as_json=False)

    def action_copy_bom_json(self) -> None:
        """Copy the currently displayed bill of materials as JSON."""
        self._copy_bom(as_json=True)

    def _copy_bom(self, *, as_json: bool) -> None:
        rows = self.query_one("#model-view", expect_type=ModelView).bom_rows
        if not rows:
            self.notify("No BOM to copy — open a model first.", severity="warning")
            return
        text = rows_to_json(rows) if as_json else rows_to_csv(rows)
        self._copy(text, f"BOM ({'JSON' if as_json else 'CSV'})")

    def action_copy_translation_csv(self) -> None:
        """Copy the complete displayed Rebrickable translation as CSV."""
        self._copy_translation(as_json=False, incomplete_only=False)

    def action_copy_translation_json(self) -> None:
        """Copy the complete displayed Rebrickable translation as JSON."""
        self._copy_translation(as_json=True, incomplete_only=False)

    def action_copy_incomplete_translation_csv(self) -> None:
        """Copy ambiguous and unresolved translation rows as CSV."""
        self._copy_translation(as_json=False, incomplete_only=True)

    def action_copy_incomplete_translation_json(self) -> None:
        """Copy ambiguous and unresolved translation rows as JSON."""
        self._copy_translation(as_json=True, incomplete_only=True)

    def _copy_translation(self, *, as_json: bool, incomplete_only: bool) -> None:
        report = self.query_one(
            "#rebrickable-translation", expect_type=RebrickableTranslation
        ).report
        if report is None:
            self.notify(
                "No Rebrickable translation to copy — open a model first.",
                severity="warning",
            )
            return
        if as_json:
            value = report.incomplete_rows if incomplete_only else report
            schema = (
                "rebrickable.ldraw.translation.incomplete"
                if incomplete_only
                else "rebrickable.ldraw.translation"
            )
            text = to_json(value, schema=schema)
        else:
            text = translation_to_csv(report, unresolved_only=incomplete_only)
        scope = "incomplete translation" if incomplete_only else "translation"
        self._copy(text, f"Rebrickable {scope} ({'JSON' if as_json else 'CSV'})")
