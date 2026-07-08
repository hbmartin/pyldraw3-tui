"""Three-pane catalog browser: categories, parts list, part detail."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical

from pyldraw3_tui.messages import (
    CategoryScope,
    CategorySelected,
    FilterChanged,
    PartHighlighted,
)
from pyldraw3_tui.widgets.category_tree import CategoryTree
from pyldraw3_tui.widgets.filter_box import FilterBox
from pyldraw3_tui.widgets.part_detail import PartDetail
from pyldraw3_tui.widgets.parts_list import PartsList

if TYPE_CHECKING:
    from ldraw.parts import CatalogEntry, Parts
    from textual.app import ComposeResult

    from pyldraw3_tui.data.search import SearchIndex


class CatalogView(Horizontal):
    """Composes the catalog widgets and keeps scope + filter in sync."""

    BINDINGS: ClassVar = [
        Binding("slash", "focus_filter", "Filter", key_display="/"),
    ]

    DEFAULT_CSS = """
    CatalogView > #catalog-sidebar {
        width: 28;
        min-width: 20;
    }
    CatalogView #category-tree {
        height: 1fr;
    }
    CatalogView #parts-list {
        width: 1fr;
        border: round $primary;
    }
    CatalogView #part-detail {
        width: 46;
        min-width: 30;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self._parts: Parts | None = None
        self._search: SearchIndex | None = None
        self._scope = CategoryScope()
        self._filter = ""

    def compose(self) -> ComposeResult:
        """Lay out sidebar, list, and detail panes."""
        with Vertical(id="catalog-sidebar"):
            yield FilterBox(id="filter-box")
            yield CategoryTree(id="category-tree")
        yield PartsList(id="parts-list")
        yield PartDetail(id="part-detail")

    def set_parts(self, parts: Parts, search: SearchIndex) -> None:
        """Populate every pane once the catalog is loaded."""
        self._parts = parts
        self._search = search
        self.query_one("#category-tree", CategoryTree).set_catalog(parts.catalog)
        self.query_one("#part-detail", PartDetail).set_parts(parts)
        self._refresh_list()

    @property
    def selected_entry(self) -> CatalogEntry | None:
        """The catalog entry under the parts-list cursor."""
        return self.query_one("#parts-list", PartsList).highlighted_entry

    def focus_part(self, code: str) -> None:
        """Reset scope/filter and move the cursor to a part code."""
        if self._parts is None:
            return
        self._scope = CategoryScope()
        self._filter = ""
        filter_box = self.query_one("#filter-box", FilterBox)
        with filter_box.prevent(FilterBox.Changed):
            filter_box.value = ""
        self._refresh_list()
        parts_list = self.query_one("#parts-list", PartsList)
        parts_list.focus_code(code)
        parts_list.focus()

    def action_focus_filter(self) -> None:
        """Move focus into the live filter box."""
        self.query_one("#filter-box", FilterBox).focus()

    @on(CategorySelected)
    def _category_selected(self, event: CategorySelected) -> None:
        event.stop()
        self._scope = event.scope
        self._refresh_list()

    @on(FilterChanged)
    def _filter_changed(self, event: FilterChanged) -> None:
        event.stop()
        self._filter = event.value
        self._refresh_list()

    @on(PartHighlighted)
    def _part_highlighted(self, event: PartHighlighted) -> None:
        event.stop()
        self.query_one("#part-detail", PartDetail).show_entry(event.entry)

    def _refresh_list(self) -> None:
        if self._parts is None:
            return
        entries = self._scope.entries(self._parts.catalog)
        if self._filter and self._search is not None:
            entries = tuple(self._search.filter(self._filter, within=entries))
        parts_list = self.query_one("#parts-list", PartsList)
        parts_list.set_entries(entries)
        parts_list.border_title = f"{self._scope.label} ({len(entries)})"
