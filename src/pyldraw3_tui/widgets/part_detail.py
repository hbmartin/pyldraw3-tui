"""Right-hand detail pane: part metadata, palette, and sub-part tree."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ldraw.errors import PartError
from rich.text import Text
from textual import work
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane

from pyldraw3_tui.data.snippets import import_snippet
from pyldraw3_tui.widgets.colour_swatches import ColourSwatches
from pyldraw3_tui.widgets.connections import PartConnections
from pyldraw3_tui.widgets.stats_panel import size_label
from pyldraw3_tui.widgets.subpart_tree import SubPartTree

if TYPE_CHECKING:
    from ldraw import PartGeometry
    from ldraw.parts import CatalogEntry, Parts
    from textual.app import ComposeResult


def _library_root(parts: Parts) -> Path | None:
    """Return the root folder that contains parts, primitives, and parts.lst."""
    parts_lst = getattr(parts, "path", None)
    if parts_lst is None:
        return None
    path = Path(parts_lst)
    return path.parent if path.name.lower() == "parts.lst" else path


def _display_path(path: Path, library_root: Path | None) -> str:
    """Prefer stable library-relative paths over machine-specific absolutes."""
    if library_root is not None:
        try:
            return path.relative_to(library_root).as_posix()
        except ValueError:
            pass
    return str(path)


def _geometry_lines(geometry: PartGeometry) -> list[tuple[str, str]]:
    """Return compact geometry and connection summary lines."""
    lines: list[tuple[str, str]] = []
    if geometry.bounds is not None:
        size = geometry.bounds.size
        lines.append(("size", size_label([size.x, size.y, size.z])))
    top_studs = sum(stud.is_top_stud for stud in geometry.studs)
    if top_studs:
        lines.append(("studs", f"{top_studs} top"))
    lines.append(("connections", str(len(geometry.connections))))
    if geometry.connection_metadata is not None:
        lines.append(("conn. coverage", geometry.connection_metadata.coverage.value))
    return lines


def _metadata_text(
    entry: CatalogEntry,
    library_root: Path | None = None,
    geometry: PartGeometry | None = None,
    geometry_error: str | None = None,
) -> Text:
    """Render an entry's metadata as labelled lines."""
    text = Text()

    def line(label: str, value: str) -> None:
        if text:
            text.append("\n")
        text.append(f"{label:>12}  ", style="bold dim")
        text.append(value)

    line("code", entry.code)
    line("description", entry.description)
    line("category", entry.category.value)
    if entry.minifig_section is not None:
        line("minifig", entry.minifig_section.value)
    if entry.keywords:
        line("keywords", ", ".join(entry.keywords))
    if geometry is not None:
        for label, value in _geometry_lines(geometry):
            line(label, value)
    elif geometry_error is not None:
        line("geometry", f"unavailable: {geometry_error}")
    if entry.part is not None:
        line("file", _display_path(Path(entry.part.path), library_root))
    if (import_line := import_snippet(entry)) is not None:
        line("import", import_line)
    return text


class PartDetail(Vertical):
    """Tabbed metadata, connections, palette, and sub-part references."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self._parts: Parts | None = None
        self._library_root: Path | None = None
        self._entry: CatalogEntry | None = None

    def compose(self) -> ComposeResult:
        """Lay out the Info and Sub-parts tabs."""
        with TabbedContent(id="detail-tabs"):
            with TabPane("Info", id="tab-info"), VerticalScroll():
                yield Static("No part selected", id="part-metadata")
                yield Static("Palette (reference)", id="palette-heading")
                yield ColourSwatches(id="palette-swatches")
            with TabPane("Connections", id="tab-connections"):
                yield PartConnections(id="part-connections")
            with TabPane("Sub-parts", id="tab-subparts"):
                yield SubPartTree(id="subpart-tree")

    def set_parts(self, parts: Parts) -> None:
        """Provide the catalog: fills the palette and enables drill-down."""
        self._parts = parts
        self._library_root = _library_root(parts)
        self.query_one("#palette-swatches", expect_type=ColourSwatches).set_palette(
            parts.colours_by_code.values(),
        )
        self.query_one("#subpart-tree", expect_type=SubPartTree).set_parts(parts)
        if self._entry is not None:
            self.show_entry(self._entry)

    def show_entry(self, entry: CatalogEntry | None) -> None:
        """Display metadata and the sub-part tree for an entry."""
        self._entry = entry
        metadata = self.query_one("#part-metadata", expect_type=Static)
        connections = self.query_one("#part-connections", expect_type=PartConnections)
        if entry is None:
            metadata.update("No part selected")
            connections.show_empty()
        else:
            metadata.update(_metadata_text(entry, self._library_root))
            if self._parts is None:
                connections.show_unavailable("Catalog not loaded.")
            else:
                connections.show_loading(entry.code)
                self._load_geometry(entry.code, self._parts)
        self.query_one("#subpart-tree", expect_type=SubPartTree).set_root_entry(entry)

    @work(thread=True, exclusive=True, group="part-geometry")
    def _load_geometry(self, code: str, parts: Parts) -> None:
        """Resolve one part off-thread and return only if it is still selected."""
        try:
            geometry = parts.geometry(code)
        except (PartError, OSError, UnicodeDecodeError) as error:
            reason = str(error) or type(error).__name__
            self.app.call_from_thread(self._geometry_failed, code, parts, reason)
            return
        self.app.call_from_thread(self._geometry_ready, code, parts, geometry)

    def _geometry_ready(
        self,
        code: str,
        parts: Parts,
        geometry: PartGeometry,
    ) -> None:
        """Render a completed geometry query if its selection is current."""
        if self._entry is None or self._entry.code != code or self._parts is not parts:
            return
        self.query_one("#part-metadata", expect_type=Static).update(
            _metadata_text(self._entry, self._library_root, geometry)
        )
        self.query_one("#part-connections", expect_type=PartConnections).show_geometry(
            geometry
        )

    def _geometry_failed(self, code: str, parts: Parts, reason: str) -> None:
        """Render a nonfatal geometry failure if its selection is current."""
        if self._entry is None or self._entry.code != code or self._parts is not parts:
            return
        self.query_one("#part-metadata", expect_type=Static).update(
            _metadata_text(
                self._entry,
                self._library_root,
                geometry_error=reason,
            )
        )
        self.query_one(
            "#part-connections", expect_type=PartConnections
        ).show_unavailable(reason)
