"""Read-only model browser: pieces, summary stats, and bill of materials."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ldraw.bom import bill_of_materials
from ldraw.model import Model
from textual import on
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Select, Static, TabbedContent, TabPane

from pyldraw3_tui.errors import ModelLoadError
from pyldraw3_tui.widgets.bom_table import BomTable
from pyldraw3_tui.widgets.piece_table import PieceTable
from pyldraw3_tui.widgets.stats_panel import StatsPanel

if TYPE_CHECKING:
    from ldraw.bom import BomRow
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

    def set_source(self, source: CatalogSource) -> None:
        """Provide the source used to open model files."""
        self._source = source

    def set_parts(self, parts: Parts) -> None:
        """Provide the catalog for descriptions and colour names."""
        self._parts = parts
        if self._model is not None:
            self._render_model()

    @property
    def bom_rows(self) -> list[BomRow]:
        """The currently displayed bill-of-materials rows."""
        return self.query_one("#bom-table", BomTable).rows_data

    def load_model(self, path: Path | str) -> None:
        """Open a model file and show its root model."""
        if self._source is None:
            return
        try:
            model = self._source.open_model(Path(path))
        except ModelLoadError as error:
            self._show_error(str(error))
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
        self.query_one("#piece-table", PieceTable).set_pieces([], self._parts)
        self.query_one("#stats-panel", StatsPanel).show_model([], self._parts)
        self.query_one("#bom-table", BomTable).set_rows([], self._parts)

    def _selected_model(self) -> Model | None:
        if self._model is None:
            return None
        if self._selected_key == ROOT_KEY:
            return self._model
        submodel = self._model.submodels.get(self._selected_key)
        if submodel is None:
            return self._model
        # Carry the root's submodel table so nested references still expand.
        return Model(
            name=submodel.name,
            objects=submodel.objects,
            submodels=dict(self._model.submodels),
        )

    def _render_model(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        pieces = list(model.iter_pieces())
        self.query_one("#piece-table", PieceTable).set_pieces(pieces, self._parts)
        self.query_one("#stats-panel", StatsPanel).show_model(pieces, self._parts)
        self.query_one("#bom-table", BomTable).set_rows(
            bill_of_materials(model, parts=self._parts),
            self._parts,
        )
