"""The pyldraw3-tui application shell: tabs, bindings, and actions."""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING, ClassVar

from ldraw.bom import rows_to_csv, rows_to_json
from textual import work
from textual.app import App
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane
from textual.worker import WorkerCancelled, WorkerFailed

from pyldraw3_tui.clipboard import copy_text
from pyldraw3_tui.commands import PyldrawTuiCommands
from pyldraw3_tui.data.search import SearchIndex
from pyldraw3_tui.data.snippets import code_snippet, import_snippet, piece_snippet
from pyldraw3_tui.data.source import CatalogSource, SourceState
from pyldraw3_tui.data.web import part_url
from pyldraw3_tui.screens.catalog import CatalogView
from pyldraw3_tui.screens.chooser import ChooserScreen, TextScreen
from pyldraw3_tui.screens.help import HelpScreen, binding_sections
from pyldraw3_tui.screens.model import ModelView
from pyldraw3_tui.screens.open_model import OpenModelScreen
from pyldraw3_tui.screens.setup import SetupScreen
from pyldraw3_tui.theme import DARK_THEME, toggled_theme
from pyldraw3_tui.widgets.category_tree import CategoryTree
from pyldraw3_tui.widgets.parts_list import PartsList
from pyldraw3_tui.widgets.subpart_tree import SubPartTree

if TYPE_CHECKING:
    from pathlib import Path

    from ldraw.parts import CatalogEntry, Parts
    from textual.app import ComposeResult
    from textual.worker import Worker

    from pyldraw3_tui.screens.help import BindingSections


class PyldrawTuiApp(App[None]):
    """Two-tab read-only browser for the LDraw catalog and model files."""

    TITLE = "pyldraw3-tui"
    COMMANDS: ClassVar = {*App.COMMANDS, PyldrawTuiCommands}
    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("1", "show_tab('catalog')", "Catalog"),
        Binding("2", "show_tab('model')", "Model"),
        Binding("y", "yank_code", "Yank code"),
        Binding("Y", "yank_chooser", "Yank…", show=False),
        Binding("o", "open_web", "ldraw.org"),
        Binding("e", "export_snippet", "Snippet"),
        Binding("colon", "command_palette", "Palette", key_display=":", show=False),
        Binding("ctrl+t", "toggle_theme", "Theme", show=False),
    ]

    def __init__(
        self,
        *,
        source: CatalogSource | None = None,
        model_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.source = (
            source if source is not None else (CatalogSource.from_default_config())
        )
        self.parts: Parts | None = None
        self.search_index: SearchIndex | None = None
        self._model_path = model_path
        self._catalog_worker: Worker[None] | None = None

    def compose(self) -> ComposeResult:
        """Lay out the header, the two tabs, and the key-hint footer."""
        yield Header()
        initial = "model" if self._model_path is not None else "catalog"
        with TabbedContent(initial=initial, id="main-tabs"):
            with TabPane("Catalog", id="catalog"):
                yield CatalogView(id="catalog-view")
            with TabPane("Model", id="model"):
                yield ModelView(id="model-view")
        yield Footer()

    def on_mount(self) -> None:
        """Classify the data source and start loading the catalog."""
        self.theme = DARK_THEME
        model_view = self.query_one("#model-view", ModelView)
        model_view.set_source(self.source)
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
        self.query_one("#catalog-view", CatalogView).loading = True
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
        self.query_one("#catalog-view", CatalogView).loading = False
        self.notify(f"Could not load the catalog: {reason}", severity="error")

    def _catalog_ready(self, parts: Parts) -> None:
        self.parts = parts
        self.search_index = SearchIndex.from_catalog(parts.catalog)
        catalog_view = self.query_one("#catalog-view", CatalogView)
        catalog_view.set_parts(parts, self.search_index)
        catalog_view.loading = False
        self.query_one("#model-view", ModelView).set_parts(parts)
        if self.query_one("#main-tabs", TabbedContent).active == "catalog":
            self.query_one("#parts-list", PartsList).focus()
        self.notify(f"Catalog loaded: {len(parts.catalog.by_code)} parts")

    # ------------------------------------------------------------- helpers

    def _selected_entry(self) -> CatalogEntry | None:
        entry = self.query_one("#catalog-view", CatalogView).selected_entry
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
        self.query_one("#main-tabs", TabbedContent).active = "catalog"
        self.query_one("#catalog-view", CatalogView).focus_part(code)

    def help_sections(self) -> BindingSections:
        """Collect binding tables for the help screen, grouped by owner."""
        return binding_sections(
            [
                ("Global", PyldrawTuiApp.BINDINGS),
                ("Catalog", CatalogView.BINDINGS),
                ("Trees", [*CategoryTree.BINDINGS, *SubPartTree.BINDINGS]),
                ("Tables", PartsList.BINDINGS),
            ],
        )

    # ------------------------------------------------------------- actions

    def action_show_tab(self, tab: str) -> None:
        """Activate the Catalog or Model tab."""
        self.query_one("#main-tabs", TabbedContent).active = tab

    def action_toggle_theme(self) -> None:
        """Switch between the dark and light themes."""
        self.theme = toggled_theme(self.theme)

    def action_help(self) -> None:
        """Show the key-binding reference."""
        self.push_screen(HelpScreen(self.help_sections()))

    def action_yank_code(self) -> None:
        """Copy the selected part's code."""
        if (entry := self._selected_entry()) is not None:
            self._copy(entry.code, f"code {entry.code}")

    def action_yank_chooser(self) -> None:
        """Choose which part field to copy."""
        if (entry := self._selected_entry()) is None:
            return
        options = [(f"Description — {entry.description}", entry.description)]
        if (import_line := import_snippet(entry)) is not None:
            options.append((f"Import — {import_line}", import_line))
        options.append((f"Code — {entry.code}", entry.code))
        self.push_screen(ChooserScreen("Copy what?", options), self._copy_choice)

    def action_export_snippet(self) -> None:
        """Choose a Python snippet form for the selected part."""
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
        """Open the selected part on library.ldraw.org."""
        if (entry := self._selected_entry()) is not None:
            webbrowser.open(part_url(entry.code))
            self.notify(f"Opened {entry.code} on ldraw.org.")

    def action_open_model_prompt(self) -> None:
        """Prompt for a model path and open it in the Model tab."""
        self.push_screen(OpenModelScreen(), self._open_model)

    def _open_model(self, path: str | None) -> None:
        if not path:
            return
        self.query_one("#main-tabs", TabbedContent).active = "model"
        self.query_one("#model-view", ModelView).load_model(path)

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
        """Copy the model's bill of materials as CSV."""
        self._copy_bom(as_json=False)

    def action_copy_bom_json(self) -> None:
        """Copy the model's bill of materials as JSON."""
        self._copy_bom(as_json=True)

    def _copy_bom(self, *, as_json: bool) -> None:
        rows = self.query_one("#model-view", ModelView).bom_rows
        if not rows:
            self.notify("No BOM to copy — open a model first.", severity="warning")
            return
        text = rows_to_json(rows) if as_json else rows_to_csv(rows)
        self._copy(text, f"BOM ({'JSON' if as_json else 'CSV'})")
