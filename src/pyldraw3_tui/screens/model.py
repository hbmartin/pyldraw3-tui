"""Read-only model browser: pieces, stats, bill of materials, and issues."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ldraw.bom import bill_of_materials
from ldraw.errors import UnknownSubmodelError
from ldraw.validation import ValidationIssue, iter_ldr_issues
from textual import on
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Select, Static, TabbedContent, TabPane

from pyldraw3_tui.errors import ModelLoadError
from pyldraw3_tui.widgets.bom_table import BomTable
from pyldraw3_tui.widgets.issues_table import IssuesTable
from pyldraw3_tui.widgets.piece_table import PieceTable
from pyldraw3_tui.widgets.stats_panel import StatsPanel

if TYPE_CHECKING:
    from ldraw.bom import BomRow
    from ldraw.model import Model
    from ldraw.parts import Parts
    from textual.app import ComposeResult

    from pyldraw3_tui.data.source import CatalogSource

ROOT_KEY = "__root__"


class ModelView(Vertical):
    """Submodel selector over tabbed Pieces / Summary / BOM panes."""

    DEFAULT_CSS = """
    ModelView > #model-topbar {
        height: 3;
        padding: 0 1;
    }
    ModelView #model-title {
        width: 1fr;
        content-align: left middle;
        height: 3;
    }
    ModelView #submodel-select {
        width: 40;
    }
    ModelView #model-error {
        display: none;
        border: round $error;
        margin: 1 2;
        padding: 1 2;
        height: auto;
    }
    ModelView.errored #model-error {
        display: block;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self._source: CatalogSource | None = None
        self._parts: Parts | None = None
        self._model: Model | None = None
        self._path: Path | None = None
        self._selected_key = ROOT_KEY

    def compose(self) -> ComposeResult:
        """Lay out the top bar and the three tabs."""
        with Horizontal(id="model-topbar"):
            yield Static("No model open — try :Open model…", id="model-title")
            yield Select[str](
                [],
                prompt="Submodel",
                allow_blank=True,
                id="submodel-select",
            )
        yield Static("", id="model-error")
        with TabbedContent(id="model-tabs"):
            with TabPane("Pieces", id="tab-pieces"):
                yield PieceTable(id="piece-table")
            with TabPane("Summary", id="tab-summary"), VerticalScroll():
                yield StatsPanel(id="stats-panel")
            with TabPane("BOM", id="tab-bom"):
                yield BomTable(id="bom-table")
            with TabPane("Issues", id="tab-issues"):
                yield IssuesTable(id="issues-table")

    def set_source(self, source: CatalogSource) -> None:
        """Provide the source used to open model files."""
        self._source = source

    def set_parts(self, parts: Parts) -> None:
        """Provide the catalog for descriptions and colour names."""
        self._parts = parts
        if self._model is not None:
            self._render_model()
        if self._path is not None:
            self._render_issues()

    @property
    def bom_rows(self) -> list[BomRow]:
        """The currently displayed bill-of-materials rows."""
        return self.query_one("#bom-table", BomTable).rows_data

    def load_model(self, path: Path | str) -> None:
        """Open a model file and show its root model."""
        if self._source is None:
            return
        self._path = Path(path)
        try:
            model = self._source.open_model(self._path)
        except ModelLoadError as error:
            self._show_error(str(error))
            self._render_issues()
            return
        self.remove_class("errored")
        self._model = model
        self._selected_key = ROOT_KEY
        title = Path(path).name
        if (description := model.description) is not None:
            title = f"{title} — {description}"
        self.query_one("#model-title", Static).update(title)
        select = self.query_one("#submodel-select", Select)
        root_label = model.name or Path(path).name
        options = [(f"(root) {root_label}", ROOT_KEY)]
        options += [(name, name) for name in model.submodels]
        with select.prevent(Select.Changed):
            select.set_options(options)
            select.value = ROOT_KEY
        self._render_model()
        self._render_issues()

    @on(Select.Changed, "#submodel-select")
    def _submodel_changed(self, event: Select.Changed) -> None:
        event.stop()
        if isinstance(event.value, str):
            self._selected_key = event.value
            self._render_model()

    def _show_error(self, message: str) -> None:
        self._model = None
        self.add_class("errored")
        self.query_one("#model-error", Static).update(f"[bold red]Error:[/] {message}")
        self.query_one("#model-title", Static).update("No model open")
        self.query_one("#piece-table", PieceTable).set_occurrences([], self._parts)
        self.query_one("#stats-panel", StatsPanel).update("Model has no pieces.")
        self.query_one("#bom-table", BomTable).set_rows([], self._parts)

    def _selected_model(self) -> Model | None:
        if self._model is None:
            return None
        if self._selected_key == ROOT_KEY:
            return self._model
        try:
            return self._model.submodel_view(self._selected_key)
        except UnknownSubmodelError:
            self._selected_key = ROOT_KEY
            select = self.query_one("#submodel-select", Select)
            with select.prevent(Select.Changed):
                select.value = ROOT_KEY
            return self._model

    def _render_model(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        steps = model.steps
        occurrences = list(
            model.iter_occurrences(include_steps=len(steps) > 1),
        )
        self.query_one("#piece-table", PieceTable).set_occurrences(
            occurrences,
            self._parts,
        )
        self.query_one("#stats-panel", StatsPanel).show_model(
            model,
            self._parts,
            steps=len(steps),
        )
        self.query_one("#bom-table", BomTable).set_rows(
            bill_of_materials(model, parts=self._parts),
            self._parts,
        )

    def _render_issues(self) -> None:
        """Validate the open file and show the issues, whole file at once.

        Validation covers the file (all submodels), not the selected
        submodel, so this runs on load — and also for files that failed
        to parse, where the issue list explains what is wrong.
        """
        if self._path is None:
            return
        try:
            issues = list(iter_ldr_issues(self._path, self._parts))
        except (OSError, UnicodeDecodeError) as error:
            issues = [
                ValidationIssue(
                    line_number=0,
                    message=f"could not re-read file: {error}",
                ),
            ]
        self.query_one("#issues-table", IssuesTable).set_issues(issues)
        tabs = self.query_one("#model-tabs", TabbedContent)
        tabs.get_tab("tab-issues").label = f"Issues ({len(issues)})"
